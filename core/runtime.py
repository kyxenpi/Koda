"""Per-request user configuration using thread-local storage."""
import threading
from typing import Any, Dict, Optional

_local = threading.local()
_CONFIG_KEY = "koda_user_config"


def set_user_config(config: Dict[str, Any]) -> None:
    setattr(_local, _CONFIG_KEY, config)


def get_user_config() -> Optional[Dict[str, Any]]:
    return getattr(_local, _CONFIG_KEY, None)


def clear_user_config() -> None:
    if hasattr(_local, _CONFIG_KEY):
        delattr(_local, _CONFIG_KEY)


def get_user_value(key: str, default: Any = None) -> Any:
    cfg = get_user_config()
    if cfg and key in cfg and cfg[key]:
        return cfg[key]
    return default
