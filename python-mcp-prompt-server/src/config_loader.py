import os
import yaml
import logging

# 确定项目根目录 (假设此文件位于 PROJECT_ROOT/src/)
# 如果 config_loader.py 相对于项目根目录的位置不同，请进行调整。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, "config.yaml") # 默认配置文件路径

# --- 默认值 ---
DEFAULTS = {
    "PROMPTS_DIR": os.path.join(PROJECT_ROOT, "prompts"), # Prompts目录路径
    "SERVER_NAME": "Python MCP Prompt Server", # 服务器名称
    "SERVER_DESCRIPTION": "Serves prompts as MCP tools, with dynamic loading and reload capability.", # 服务器描述
    "LOG_LEVEL": "INFO", # 日志级别 (字符串形式, 稍后转换为 logging 级别)
    "LOG_FORMAT": "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s" # 日志格式 (添加了文件名/行号)
}

# 全局配置缓存
_config = None
_logger_configured = False # 标记以确保 basicConfig 只被调用一次

def load_config(config_path: str = DEFAULT_CONFIG_FILE_PATH) -> dict:
    """从YAML文件、环境变量和默认值加载配置。"""
    yaml_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {} # 确保即使文件为空/无效，也是一个字典
        except yaml.YAMLError as e:
            # 此处使用 print 是因为 logger 可能尚未配置，或者使用备用 logger
            print(f"警告: 解析YAML配置文件 '{config_path}' 失败: {e}。将使用默认值和环境变量。")
        except Exception as e:
            print(f"警告: 无法读取配置文件 '{config_path}': {e}。将使用默认值和环境变量。")
    
    if not isinstance(yaml_config, dict):
        print(f"警告: 配置文件 '{config_path}' 未产生字典。将使用默认值和环境变量。")
        yaml_config = {}

    # 解析配置，优先级: 环境变量 > YAML > 默认值
    resolved_config = {}
    for key, default_value in DEFAULTS.items():
        env_var_name = f"MCP_SERVER_{key}" # 修改前缀为 MCP_SERVER_ 以增加清晰度
        env_value = os.environ.get(env_var_name)
        # 对于布尔类型，os.environ.get 可能返回 "False" 或 "True" 字符串。
        # 此简单加载器不自动转换除 YAML 解析所做转换之外的类型。
        # LOG_LEVEL 在 logger 设置时处理。其他的是字符串或路径。

        yaml_value = yaml_config.get(key)

        if env_value is not None:
            resolved_config[key] = env_value
        elif yaml_value is not None:
            resolved_config[key] = yaml_value
        else:
            resolved_config[key] = default_value
    
    # 确保 PROMPTS_DIR 是绝对路径
    # 如果来自环境或YAML的 PROMPTS_DIR 是相对路径，则相对于 PROJECT_ROOT 解析它
    prompts_dir_value = resolved_config["PROMPTS_DIR"]
    if not os.path.isabs(prompts_dir_value):
        # 假设相对路径是相对于 PROJECT_ROOT
        resolved_config["PROMPTS_DIR"] = os.path.abspath(os.path.join(PROJECT_ROOT, prompts_dir_value))
    else: # 如果来自环境/YAML的路径是绝对路径，则按原样使用。如果是默认值，则已经是绝对路径。
        resolved_config["PROMPTS_DIR"] = os.path.abspath(prompts_dir_value)

    return resolved_config

def get_config() -> dict:
    """返回缓存的配置，如果需要则加载它。"""
    global _config
    if _config is None:
        # 允许通过环境变量覆盖配置文件路径，用于测试或特殊设置
        config_file_override = os.environ.get("MCP_SERVER_CONFIG_FILE", DEFAULT_CONFIG_FILE_PATH)
        _config = load_config(config_file_override)
    return _config

def get_logger(name: str) -> logging.Logger:
    """根据加载的配置配置并返回一个 logger 实例。"""
    global _logger_configured
    config = get_config() # 确保配置已加载
    
    log_level_str = str(config.get("LOG_LEVEL", DEFAULTS["LOG_LEVEL"])).upper()
    # 确保 log_level_str 是一个有效的级别名称
    if not hasattr(logging, log_level_str):
        print(f"警告: 无效的 LOG_LEVEL '{log_level_str}'。默认为 INFO。")
        log_level_str = "INFO"
    log_level = getattr(logging, log_level_str) # 如果仍然无效，则默认为 INFO
    
    log_format = str(config.get("LOG_FORMAT", DEFAULTS["LOG_FORMAT"]))

    # 仅配置一次根 logger
    if not _logger_configured:
        # 移除与根 logger 关联的所有处理器
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # 添加新的 basicConfig
        logging.basicConfig(level=log_level, format=log_format)
        
        # 例如，如果使用文件日志:
        # logging.basicConfig(filename=config.get("LOG_FILE", "server.log"), 
        #                     level=log_level, format=log_format)
        
        # 对于更复杂的场景，可以直接配置处理器:
        # logger_instance = logging.getLogger() # 获取根 logger
        # logger_instance.setLevel(log_level)
        # ch = logging.StreamHandler()
        # ch.setLevel(log_level)
        # formatter = logging.Formatter(log_format)
        # ch.setFormatter(formatter)
        # logger_instance.addHandler(ch)
        # # 如果也记录到文件:
        # # fh = logging.FileHandler(config.get("LOG_FILE", "server.log"))
        # # fh.setFormatter(formatter)
        # # logger_instance.addHandler(fh)

        _logger_configured = True
        
    return logging.getLogger(name)

if __name__ == '__main__':
    # 示例用法和测试打印
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"默认配置文件路径: {DEFAULT_CONFIG_FILE_PATH}")

    # 使用环境变量覆盖进行测试
    os.environ["MCP_SERVER_SERVER_NAME"] = "来自环境的测试服务器"
    os.environ["MCP_SERVER_LOG_LEVEL"] = "DEBUG" # 测试日志级别覆盖

    # 测试 YAML 加载, 需要在项目根目录创建一个虚拟的 config.yaml
    # 例如, 创建 PROJECT_ROOT/config.yaml 内容如下:
    # SERVER_NAME: "来自YAML的测试服务器"
    # PROMPTS_DIR: "custom_prompts_yaml" 
    
    # 为了本次自我运行，模拟一个配置文件以直接测试 load_config
    test_config_content = {
        "SERVER_NAME": "我的YAML服务器",
        "LOG_LEVEL": "WARNING",
        "PROMPTS_DIR": "yaml_prompts" # 相对路径示例
    }
    dummy_config_path = os.path.join(PROJECT_ROOT, "dummy_config_test.yaml")
    with open(dummy_config_path, 'w', encoding='utf-8') as f:
        yaml.dump(test_config_content, f)

    # 直接测试加载此虚拟配置 (get_config 会使用 DEFAULT_CONFIG_FILE_PATH 或环境变量覆盖)
    # 我们需要清除全局 _config 以强制使用虚拟路径重新加载进行此测试运行
    _config = None 
    # 设置配置文件路径的环境变量指向我们的虚拟文件进行此测试
    os.environ["MCP_SERVER_CONFIG_FILE"] = dummy_config_path
    
    config = get_config() # 现在应该由于环境变量而加载 dummy_config_test.yaml

    print("\n加载的配置 (使用 dummy_config_test.yaml 和环境变量):")
    for k, v in config.items():
        print(f"  {k}: {v}")
    
    # 清理虚拟配置文件
    if os.path.exists(dummy_config_path):
        os.remove(dummy_config_path)
    # 取消设置配置文件路径的环境变量
    del os.environ["MCP_SERVER_CONFIG_FILE"]
    # 取消设置其他测试环境变量
    del os.environ["MCP_SERVER_SERVER_NAME"]
    del os.environ["MCP_SERVER_LOG_LEVEL"]
    _config = None # 重置配置缓存以供后续调用 (如果有)

    print("\n重新检查配置 (应该是默认值或实际的 config.yaml (如果存在)，没有虚拟/环境变量覆盖):")
    # 现在将根据实际的 config.yaml 或默认值加载，因为环境变量已被清除
    default_run_config = get_config()
    for k, v in default_run_config.items():
        print(f"  {k}: {v}")

    logger = get_logger(__name__) # Logger 将使用最新的配置状态 (default_run_config)
    logger.info("来自 config_loader 的测试 info 消息 (在虚拟/环境变量测试之后)。")
    logger.warning("来自 config_loader 的测试 warning 消息。")
    logger.debug("如果 LOG_LEVEL 是来自默认/config.yaml 的 INFO/WARNING，则此 debug 消息可能不会显示。")
    logger.error("这是一个 error 日志测试。")
    logger.critical("这是一个 critical 日志测试。")

    print(f"\n'{logger.name}' 的日志级别是: {logging.getLevelName(logger.getEffectiveLevel())}")
    print(f"根 logger 级别: {logging.getLevelName(logging.getLogger().getEffectiveLevel())}")
    print(f"根 logger 处理器: {logging.getLogger().handlers}")

    # 测试来自默认值的相对 PROMPTS_DIR 解析
    _config = None # 强制重新加载
    os.environ["MCP_SERVER_PROMPTS_DIR"] = "relative_prompts_dir_test"
    rel_config = get_config()
    print(f"\n测试来自环境的相对 PROMPTS_DIR: {rel_config['PROMPTS_DIR']}")
    expected_abs_path = os.path.abspath(os.path.join(PROJECT_ROOT, "relative_prompts_dir_test"))
    print(f"预期的绝对路径: {expected_abs_path}")
    assert rel_config['PROMPTS_DIR'] == expected_abs_path
    del os.environ["MCP_SERVER_PROMPTS_DIR"]
    _config = None # 清理
    print("相对路径测试成功。")

    print("\nConfig loader 测试完成。")
