import os
from main import app
from database.memory_db import db
from core.logger import setup_logger

logger = setup_logger("WSGI")

# Cleanup old sessions on startup
try:
    deleted = db.cleanup_old_sessions(keep_days=30)
    if deleted > 0:
        logger.info(f"Cleanup: {deleted} mensagens antigas removidas")
except Exception as e:
    logger.warning(f"Cleanup inicial ignorado: {e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
