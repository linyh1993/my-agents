import logging
import os
from typing import Dict

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, "config.yaml")

DEFAULTS = {
    "PROMPTS_DIR": os.path.join(PROJECT_ROOT, "prompts"),
    "SERVER_NAME": "Python MCP Prompt Server",
    "SERVER_DESCRIPTION": "Serves prompts as MCP tools, with dynamic loading and reload capability.",
}

def load_config(config_path: str = DEFAULT_CONFIG_FILE_PATH) -> Dict:
    """Load configuration from YAML file, environment variables and defaults."""
    yaml_config = {}
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {}
        except (yaml.YAMLError, Exception) as e:
            logger.warning(f"无法加载配置文件 '{config_path}': {e}。将使用默认值和环境变量。")
            yaml_config = {}
    
    if not isinstance(yaml_config, dict):
        logger.warning(f"配置文件 '{config_path}' 未生成有效的字典。将使用默认值和环境变量。")
        yaml_config = {}
    
    resolved_config = {}
    for key, default_value in DEFAULTS.items():
        env_var_name = f"MCP_SERVER_{key}"
        resolved_config[key] = os.environ.get(env_var_name) or yaml_config.get(key) or default_value
    
    prompts_dir = resolved_config["PROMPTS_DIR"]
    resolved_config["PROMPTS_DIR"] = os.path.abspath(os.path.join(PROJECT_ROOT, prompts_dir) if not os.path.isabs(prompts_dir) else prompts_dir)
    
    return resolved_config

