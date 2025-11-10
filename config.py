import json

CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    'max_retries': 3,
    'backoff_base': 3
}

def _get_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                config.setdefault(key, value)
            return config
    except FileNotFoundError:
        return DEFAULT_CONFIG

def _save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def set_config_value(key, value):
    if key not in DEFAULT_CONFIG:
        print(f"Error: '{key}' is not a valid config option.")
        return
        
    config = _get_config()
    
    try:
        config[key] = type(DEFAULT_CONFIG[key])(value)
        _save_config(config)
        print(f"Config updated: {key} = {config[key]}")
    except ValueError:
        print(f"Error: Invalid value type for '{key}'. Expected {type(DEFAULT_CONFIG[key])}.")

def get_config_value(key):
    config = _get_config()
    return config.get(key)