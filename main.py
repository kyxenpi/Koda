import os
import time
from flask import Flask, jsonify, request
from flask_cors import CORS
from routes.web import web_blueprint
from routes.telegram import telegram_blueprint
from core.logger import setup_logger
from config import settings

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = setup_logger("AppInit")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app)

# --- Rate limiting via IP ---
_request_times: dict = {}

def _check_rate_limit() -> bool:
    if settings.RATE_LIMIT == "0":
        return True
    try:
        parts = settings.RATE_LIMIT.split()
        max_req = int(parts[0])
        period = parts[2] if len(parts) > 2 else "minute"
        window = {"second": 1, "minute": 60, "hour": 3600}.get(period, 60)
    except (ValueError, IndexError):
        return True

    ip = request.remote_addr or "unknown"
    now = time.time()
    if ip not in _request_times:
        _request_times[ip] = []
    _request_times[ip] = [t for t in _request_times[ip] if now - t < window]
    if len(_request_times[ip]) >= max_req:
        return False
    _request_times[ip].append(now)
    return True


@app.before_request
def rate_limit():
    if request.endpoint and request.endpoint != "health":
        if not _check_rate_limit():
            return jsonify({"erro": "Muitas requisições. Aguarde um momento."}), 429


@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "version": "2.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "database": "postgresql" if (settings.DATABASE_URL or "").startswith("postgres") else "sqlite",
    })


app.register_blueprint(web_blueprint)
app.register_blueprint(telegram_blueprint)

if __name__ == '__main__':
    port = int(os.getenv("PORT", "5000"))
    logger.info(f"Iniciando Koda Agent Core Server na porta {port}...")
    app.run(debug=True, host="0.0.0.0", port=port)
