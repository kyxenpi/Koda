import json
import hashlib
from typing import List, Dict, Any, Tuple, Generator

from config import settings
from agent.models import model_manager
from agent.executor import tool_executor
from agent.context import ContextManager
from agent.reflection import ReflectionEngine
from database.memory_db import db
from core.logger import setup_logger
from tools.base import registry, IS_CLOUD

logger = setup_logger("AgentCore")


class Agent:
    def __init__(self) -> None:
        self.max_steps = settings.MAX_AGENT_STEPS

    def _execute_tool_calls(
        self, session_id: str, tool_call: Dict[str, Any], last_tool_hash: str | None
    ) -> Tuple[List[Dict[str, Any]], str | None]:
        tool_results = []
        nova_chamada = None
        comentario = tool_call.get("comentario", "Executando ferramentas.")

        for call in tool_call["tool_calls"]:
            tool_name = call.get("tool", "")
            tool_args = call.get("args", {})

            if tool_name not in registry.tools:
                tool_results.append({"tool": tool_name, "success": False, "error": "Ferramenta inexistente."})
                continue

            if IS_CLOUD and not registry.tools[tool_name]["cloud_compatible"]:
                tool_results.append({"tool": tool_name, "success": False, "error": "Indisponível na nuvem."})
                continue

            chave = hashlib.sha256(f"{tool_name}|{json.dumps(tool_args, sort_keys=True)}".encode()).hexdigest()
            if chave == last_tool_hash:
                tool_results.append({"tool": tool_name, "success": False, "error": "Chamada repetida consecutiva."})
                continue
            last_tool_hash = chave

            result = tool_executor.execute(tool_name, tool_args)
            tool_results.append({
                "tool": tool_name, "success": result.success,
                "output": result.output, "error": result.error
            })

            if tool_executor.extract_tool_calls(result.output):
                nova_chamada = result.output

        db.save_message(session_id, "system",
            "Resultado das ferramentas:\n" + json.dumps(tool_results, ensure_ascii=False, indent=2))

        if nova_chamada:
            db.save_message(session_id, "system",
                "Nota: Uma ferramenta retornou uma solicitação de nova ferramenta. Processe se necessário.")

        return tool_results, last_tool_hash

    def _execute_cycle(
        self, session_id: str, user_message: str
    ) -> Generator[Dict[str, Any], None, Tuple[str, List[Dict[str, Any]] | None]]:
        execution_flow: List[Dict[str, Any]] = []
        step = 0
        last_tool_hash = None
        final_text = ""

        while step < self.max_steps:
            step += 1
            context = ContextManager.build(session_id)

            try:
                resposta = model_manager.execute_completion(context)
            except Exception as e:
                logger.error(f"LLM execution failed: {e}")
                yield {"type": "error", "content": f"Erro na IA: {e}"}
                return f"Erro na IA: {e}", []

            tool_call = tool_executor.extract_tool_calls(resposta)

            if tool_call and "tool_calls" in tool_call:
                comentario = tool_call.get("comentario", "Executando ferramentas.")
                yield {"type": "thinking", "content": comentario}
                execution_flow.append({"type": "jarvis", "content": comentario})

                for call in tool_call["tool_calls"]:
                    yield {"type": "tool_call", "tool": call.get("tool", ""), "args": call.get("args", {})}
                    execution_flow.append({
                        "type": "tool_call",
                        "tool_name": call.get("tool", ""),
                        "tool_args": call.get("args", {})
                    })

                tool_results, last_tool_hash = self._execute_tool_calls(
                    session_id, tool_call, last_tool_hash
                )

                for tr in tool_results:
                    if tr["success"]:
                        yield {"type": "tool_result", "tool": tr["tool"], "output": tr.get("output", "")}
                    else:
                        yield {"type": "tool_error", "tool": tr["tool"], "error": tr.get("error", "")}

                execution_flow.append({"type": "tool_results", "content": tool_results})

                if step >= self.max_steps:
                    last_t = tool_results[-1] if tool_results else {}
                    final_text = last_t.get("output") or last_t.get("error") or "Execução concluída."
                    yield {"type": "done", "content": final_text}
                    db.save_message(session_id, "assistant", final_text)
                    return final_text, execution_flow

                yield {"type": "status", "content": "processing"}
                continue

            # Resposta direta do LLM
            if step == 1:
                yield {"type": "streaming"}
                full = ""
                for token in model_manager.stream_completion(context):
                    full += token
                    yield {"type": "token", "content": token}
                yield {"type": "done", "content": full}
                db.save_message(session_id, "assistant", full)
                return full, execution_flow

            # Reflexão
            meta = ReflectionEngine.verify_goal(user_message, resposta)
            if meta:
                yield {"type": "streaming"}
                full = ""
                for token in model_manager.stream_completion(context):
                    full += token
                    yield {"type": "token", "content": token}
                yield {"type": "done", "content": full}
                db.save_message(session_id, "assistant", full)
                return full, execution_flow

            yield {"type": "thinking", "content": "Reavaliando..."}
            db.save_message(session_id, "system",
                "Sua resposta não concluiu o objetivo. Use os resultados das ferramentas e responda.")
            execution_flow.append({"type": "jarvis", "content": "Reavaliando..."})

        # Esgotou ciclos
        if execution_flow:
            for item in reversed(execution_flow):
                if item["type"] == "jarvis" and isinstance(item["content"], str) and item["content"].strip():
                    final_text = item["content"]
                    break
        final_text = final_text or "Processamento concluído."
        yield {"type": "done", "content": final_text}
        db.save_message(session_id, "assistant", final_text)
        return final_text, execution_flow

    def process(self, session_id: str, user_message: str) -> Tuple[str, List[Dict[str, Any]]]:
        db.save_message(session_id, "user", user_message)
        gen = self._execute_cycle(session_id, user_message)
        final_text = ""
        execution_flow = []
        for event in gen:
            if event["type"] == "done":
                final_text = event["content"]
            execution_flow.append(event)
        return final_text or "Processamento concluído.", execution_flow

    def stream_process(self, session_id: str, user_message: str) -> Generator[Dict[str, Any], None, None]:
        yield {"type": "status", "content": "thinking"}
        db.save_message(session_id, "user", user_message)
        gen = self._execute_cycle(session_id, user_message)
        yield from gen


koda_agent = Agent()
