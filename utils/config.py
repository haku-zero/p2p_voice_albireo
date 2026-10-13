import json
import os

CONFIG_FILE = os.environ.get("ALBIREO_CONFIG", "settings.json")

def set_profile(profile_name):
    global CONFIG_FILE
    if profile_name:
        CONFIG_FILE = f"settings_{profile_name}.json"
        os.environ["ALBIREO_CONFIG"] = CONFIG_FILE
        os.environ["ALBIREO_DB"] = f"albireo_state_{profile_name}.db"
    else:
        CONFIG_FILE = "settings.json"
        os.environ["ALBIREO_CONFIG"] = CONFIG_FILE
        os.environ["ALBIREO_DB"] = "albireo_state.db"

def load_config():
    file_path = os.environ.get("ALBIREO_CONFIG", CONFIG_FILE)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(key, value):
    cfg = load_config()
    cfg[key] = value
    file_path = os.environ.get("ALBIREO_CONFIG", CONFIG_FILE)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
