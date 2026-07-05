import os
import uuid
import json
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, Response
from agent.agent import koda_agent
from agent.models import model_manager
from core.utils import get_system_telemetry
from agent.image_process import read_image
from database.memory_db import db
from core.runtime import set_user_config, clear_user_config, get_user_config

web_blueprint = Blueprint('web', __name__)


@web_blueprint.route('/')
def index():
    return render_template('index.html')


def _extract_user_config() -> dict:
    cfg = {}
    if request.is_json:
        dados = request.get_json(silent=True) or {}
    else:
        dados = request.form.to_dict()

    for key in ("groq_api_key", "ocr_api_key", "google_credentials", "google_token"):
        val = dados.get(key) or request.headers.get(f"X-{key.replace('_', '-').title()}")
        if val:
            cfg[key] = val
    return cfg


def _inject_config():
    cfg = _extract_user_config()
    if cfg:
        set_user_config(cfg)


def _process_image(mensagem: str) -> str:
    if 'imagem' not in request.files:
        return mensagem
    arquivo_img = request.files['imagem']
    if not arquivo_img or not arquivo_img.filename:
        return mensagem

    ext = Path(arquivo_img.filename).suffix if '.' in arquivo_img.filename else ''
    temp_filename = f"/tmp/koda_web_{uuid.uuid4().hex}{ext}"
    try:
        arquivo_img.save(temp_filename)
        resultado_ocr = read_image(temp_filename)
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

        if resultado_ocr.get("success") and resultado_ocr.get("output"):
            texto_extraido = resultado_ocr["output"]
            prompt_final = f"[Texto extraído da imagem enviada pelo usuário]:\n{texto_extraido}"
            if mensagem:
                prompt_final += f"\n\n[Comando/Mensagem do usuário]: {mensagem}"
            return prompt_final
        else:
            if mensagem:
                return f"[Sistema: Uma imagem foi anexada, mas nenhum texto foi extraído dela]. Comando do usuário: {mensagem}"
            return "[Sistema: O usuário enviou uma imagem vazia ou sem texto legível]."
    except Exception as e:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        raise


@web_blueprint.route('/chat', methods=['POST'])
def chat_web():
    _inject_config()
    try:
        if request.is_json:
            dados = request.get_json() or {}
            mensagem = dados.get("mensagem", "")
            session_id = dados.get("session_id", "web_default_session")
        else:
            mensagem = request.form.get("mensagem", "")
            session_id = request.form.get("session_id", "web_default_session")

        try:
            mensagem = _process_image(mensagem)
        except Exception as e:
            return jsonify({"erro": f"Erro ao processar imagem: {str(e)}"}), 500

        if not mensagem:
            return jsonify({"erro": "Nenhuma mensagem ou imagem foi enviada"}), 400

        resposta_texto, fluxo = koda_agent.process(session_id, mensagem)
        return jsonify({"fluxo": fluxo, "resposta": resposta_texto})
    finally:
        clear_user_config()


@web_blueprint.route('/chat/stream', methods=['POST'])
def chat_stream():
    _inject_config()
    if request.is_json:
        dados = request.get_json() or {}
        mensagem = dados.get("mensagem", "")
        session_id = dados.get("session_id", "web_default_session")
    else:
        mensagem = request.form.get("mensagem", "")
        session_id = request.form.get("session_id", "web_default_session")

    try:
        mensagem = _process_image(mensagem)
    except Exception as e:
        def err():
            yield f"data: {json.dumps({'type': 'error', 'content': f'Erro ao processar imagem: {str(e)}'})}\n\n"
        return Response(err(), mimetype='text/event-stream')

    if not mensagem:
        def empty():
            yield f"data: {json.dumps({'type': 'error', 'content': 'Nenhuma mensagem ou imagem foi enviada'})}\n\n"
        return Response(empty(), mimetype='text/event-stream')

    def generate():
        try:
            for event in koda_agent.stream_process(session_id, mensagem):
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            clear_user_config()

    return Response(generate(), mimetype='text/event-stream')


@web_blueprint.route('/debug/config', methods=['GET', 'POST'])
def debug_config():
    if request.method == 'POST':
        _inject_config()
    try:
        cfg = get_user_config() or {}
        has_groq = bool(cfg.get("groq_api_key"))
        return jsonify({
            "has_user_config": bool(cfg),
            "has_groq_key": has_groq,
            "groq_prefix": (cfg.get("groq_api_key", "")[:12] + "...") if has_groq else None,
            "form_keys": list(request.form.keys()) if request.form else [],
        })
    finally:
        if request.method == 'POST':
            clear_user_config()


@web_blueprint.route('/admin/cleanup', methods=['POST'])
def admin_cleanup():
    try:
        dias = request.get_json(silent=True) or {}
        keep_days = int(dias.get("keep_days", 30))
        deleted = db.cleanup_old_sessions(keep_days=keep_days)
        return jsonify({"removidas": deleted, "keep_days": keep_days})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@web_blueprint.route('/telemetria', methods=['GET'])
def telemetria():
    return jsonify(get_system_telemetry())


@web_blueprint.route('/transcrever', methods=['POST'])
def transcrever_audio():
    _inject_config()
    try:
        if 'audio' not in request.files:
            return jsonify({"erro": "Nenhum arquivo enviado"}), 400

        arquivo = request.files['audio']
        texto = model_manager.transcrever_audio(arquivo.filename, arquivo.read())
        return jsonify({"texto": texto})
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    finally:
        clear_user_config()
