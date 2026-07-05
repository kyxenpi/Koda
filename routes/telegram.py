import os
import json
import uuid
import requests
from flask import Blueprint, request
from agent.agent import koda_agent
from agent.executor import tool_executor
from config import settings
from agent.image_process import read_image

telegram_blueprint = Blueprint('telegram', __name__)


@telegram_blueprint.route('/webhook', methods=['POST'])
def telegram_webhook():
    token = getattr(settings, 'TELEGRAM_TOKEN', None) or os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        return 'Token não configurado', 500

    try:
        dados_update = request.get_json(silent=True) or json.loads(request.data.decode('utf-8'))

        if dados_update and "message" in dados_update:
            message = dados_update["message"]
            chat_id = str(message["chat"]["id"])
            base_url = f"https://api.telegram.org/bot{token}"

            texto_usuario = ""

            # --- FOTO ---
            if "photo" in message:
                try:
                    requests.post(f"{base_url}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
                except Exception:
                    pass

                photo_file_id = message["photo"][-1]["file_id"]
                legenda = message.get("caption", "")

                try:
                    res_file = requests.get(f"{base_url}/getFile", params={"file_id": photo_file_id}, timeout=10).json()
                    if res_file.get("ok"):
                        file_path = res_file["result"]["file_path"]
                        download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                        img_data = requests.get(download_url, timeout=15).content
                        temp_filename = f"/tmp/koda_tg_{uuid.uuid4().hex}.jpg"

                        with open(temp_filename, "wb") as f:
                            f.write(img_data)

                        resultado_ocr = read_image(temp_filename)

                        if os.path.exists(temp_filename):
                            os.remove(temp_filename)

                        if resultado_ocr.get("success") and resultado_ocr.get("output"):
                            texto_extraido = resultado_ocr["output"]
                            texto_usuario = f"[Texto extraído da imagem enviada pelo usuário]:\n{texto_extraido}"
                            if legenda:
                                texto_usuario += f"\n\n[Comando/Legenda do usuário]: {legenda}"
                        else:
                            texto_usuario = "[Sistema]: O usuário enviou uma imagem, mas nenhum texto pôde ser extraído dela."
                            if legenda:
                                texto_usuario += f" O usuário deixou a seguinte legenda: {legenda}"
                    else:
                        texto_usuario = "Erro: Não foi possível obter o link da imagem nos servidores do Telegram."
                except Exception as img_err:
                    texto_usuario = "Erro: Falha interna ao processar a sua imagem."

            # --- TEXTO PURO ---
            elif "text" in message:
                texto_usuario = message["text"]

            if not texto_usuario:
                return 'OK', 200

            try:
                requests.post(f"{base_url}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
            except Exception:
                pass

            # Usa process() em vez de stream_process() porque é síncrono via webhook
            _, fluxo = koda_agent.process(chat_id, texto_usuario)

            # Envia updates intermediários para o Telegram
            for etapa in fluxo:
                if etapa["type"] in ("thinking",) and etapa.get("content"):
                    try:
                        requests.post(f"{base_url}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": etapa["content"],
                            "parse_mode": "Markdown"
                        }, timeout=5)
                    except Exception:
                        pass

            # Extrai a resposta final do último evento "done"
            resposta_texto = ""
            for etapa in reversed(fluxo):
                if etapa["type"] == "done":
                    resposta_texto = etapa.get("content", "")
                    break

            if resposta_texto:
                if len(resposta_texto) > 1000:
                    resposta_texto = (
                        "Resposta muito longa, resumo:\n\n" +
                        resposta_texto[:400] + "...\n\n"
                    )

                requests.post(f"{base_url}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": resposta_texto,
                    "parse_mode": "Markdown"
                }, timeout=5)

        return 'OK', 200
    except Exception as e:
        return 'Erro Interno', 500
