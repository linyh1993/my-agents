"""
Python MCP Prompt Server 的主要服务器逻辑。
处理从提示定义动态创建和注册 MCP 工具，
并提供用于重新加载提示和列出可用提示的管理工具。
"""
import os
import re
from typing import List, Dict, Any, Callable, Optional as TypingOptional # 显式导入 TypingOptional 以用于类型提示
from fastmcp import FastMCP
from src.prompt_loader import load_prompts_from_directory
from src.config_loader import get_config, get_logger # 导入新的配置函数
# 导入新的动态工具生成器模块
from .dynamic_tool_generator import create_and_register_prompt_tool 

# --- 加载配置 ---
config = get_config()
logger = get_logger(__name__) # 使用配置好的 logger

# --- 从配置中获取常量和全局变量 ---
SERVER_NAME = config["SERVER_NAME"]
SERVER_DESCRIPTION = config["SERVER_DESCRIPTION"]
PROMPTS_DIR = config["PROMPTS_DIR"] # 此路径已由 config_loader 解析为绝对路径

# 全局 FastMCP 实例
# 注意: SERVER_NAME 和 SERVER_DESCRIPTION 现在来自配置
mcp = FastMCP(name=SERVER_NAME, description=SERVER_DESCRIPTION)

# 全局字典，用于跟踪为每个提示工具创建的 Python 函数。
# 键: 原始提示名称。值: 动态生成的 Python 函数对象。
REGISTERED_TOOL_FUNCTIONS: Dict[str, Callable[..., Any]] = {}


# --- 核心服务器管理工具 ---
# 注意: _sanitize_for_python_identifier, _prepare_function_parameters, 
#       _generate_dynamic_function_code, 和旧的 create_and_register_prompt_tool
#       已移至 dynamic_tool_generator.py

@mcp.tool(name="get_prompt_names", description="列出所有当前可用的基于提示的工具的名称。")
def get_prompt_names() -> List[str]:
    """
    检索所有当前可用的基于提示的工具的名称列表，
    不包括服务器管理工具，如 'reload_prompts' 和 'get_prompt_names'。
    """
    if not hasattr(mcp, 'tools') or not hasattr(mcp.tools, 'keys'): # 检查 .keys() 方法
        logger.warning("MCP 工具注册表未找到或不是有效的 ToolManager。无法列出提示名称。")
        return []
    
    all_tool_names = list(mcp.tools.keys())
    management_tool_names = {"reload_prompts", "get_prompt_names"} # 管理工具名称集合
    prompt_tool_names = [name for name in all_tool_names if name not in management_tool_names]
    return prompt_tool_names

def _reregister_management_tools(mcp_instance: FastMCP):
    """辅助函数，用于在清除注册表后重新注册必要的服务器管理工具。"""
    mcp_instance.tool(name="reload_prompts", description="从 prompts 目录重新加载所有提示工具。")(reload_all_prompts)
    mcp_instance.tool(name="get_prompt_names", description="列出所有当前可用的基于提示的工具的名称。")(get_prompt_names)
    # logger.info("重新注册了必要的服务器工具。")

def _clear_registered_tools(mcp_instance: FastMCP, registered_tool_functions_dict: Dict[str, Callable[..., Any]]):
    """从 FastMCP 和内部跟踪字典中清除所有已注册的工具。"""
    if hasattr(mcp_instance, 'tools') and hasattr(mcp_instance.tools, 'clear'):
        mcp_instance.tools.clear() # 调用 ToolManager 的 clear 方法
        registered_tool_functions_dict.clear()
        logger.info("已从注册表和内部跟踪中清除现有工具。")
    else:
        # 这种情况意味着 FastMCP 实例或其版本/结构存在问题。
        logger.critical("无法清除 FastMCP 工具注册表 (tools 属性缺失或没有 clear 方法)。重新加载可能会导致重复或错误。")

def _load_and_register_prompt_tools(prompts_dir: str, mcp_instance: FastMCP) -> int:
    """从目录加载提示并将其注册为工具。"""
    loaded_prompts_data = load_prompts_from_directory(prompts_dir)
    num_registered = 0
    
    if not loaded_prompts_data:
        status_msg = f"提示目录 '{prompts_dir}' 为空或不包含有效提示。未加载任何动态工具。"
    else:
        logger.info(f"从 '{prompts_dir}' 找到 {len(loaded_prompts_data)} 个要处理的提示定义。")
        for p_data in loaded_prompts_data:
            try:
                # 更新调用以传递 logger 和 REGISTERED_TOOL_FUNCTIONS
                create_and_register_prompt_tool(
                    p_data, 
                    mcp_instance, 
                    logger, 
                    REGISTERED_TOOL_FUNCTIONS
                )
                num_registered += 1
            except Exception as e: # 捕获循环期间的全部异常以确保安全
                prompt_name = p_data.get('name', '未命名提示')
                logger.error(f"为提示 '{prompt_name}' 创建/注册工具失败: {e}", exc_info=True)
        status_msg = f"已成功从 '{prompts_dir}' 注册 {num_registered} 个动态工具。"
    
    logger.info(status_msg)
    return num_registered

@mcp.tool(name="reload_prompts", description="从 prompts 目录重新加载所有提示工具。")
def reload_all_prompts() -> str:
    """
    清除现有的基于提示的工具，从 PROMPTS_DIR 重新加载所有提示，
    并将它们注册为新工具。必要的管理工具也会被重新注册。
    """
    global REGISTERED_TOOL_FUNCTIONS # _clear_registered_tools 会修改它，因此必需
    logger.info(f"正在从目录重新加载提示: {PROMPTS_DIR}...")
    
    _clear_registered_tools(mcp, REGISTERED_TOOL_FUNCTIONS)
    
    _load_and_register_prompt_tools(PROMPTS_DIR, mcp)
    
    _reregister_management_tools(mcp) # 确保管理工具始终可用
    
    final_tool_count = len(get_prompt_names()) # get_prompt_names 不包括管理工具
    status_msg = f"提示已重新加载。{final_tool_count} 个动态工具可用。管理工具已重新注册。"
    logger.info(status_msg)
    return status_msg


# --- 服务器初始化和启动 ---
def _ensure_prompts_directory_exists():
    """
    检查 PROMPTS_DIR 是否存在，如果不存在则创建它，并在新创建时添加示例提示。
    使用全局配置的 PROMPTS_DIR。
    """
    # PROMPTS_DIR 现在来自配置模块
    if not os.path.exists(PROMPTS_DIR):
        logger.info(f"提示目录 '{PROMPTS_DIR}' 未找到。正在创建它...")
        try:
            os.makedirs(PROMPTS_DIR)
            logger.info(f"成功创建提示目录: {PROMPTS_DIR}")
            # 创建一个示例提示以指导用户并用于初始测试。
            example_prompt_content = """
name: "Example Greeting Prompt"
description: "Generates a personalized greeting (example)."
arguments:
  - name: "user_name"
    description: "The name of the person to greet."
    type: "string"
    required: true
  - name: "time_of_day"
    description: "Time of day (e.g., morning, afternoon, evening)."
    type: "string"
    required: false
    default: "day" # Example of a default value
prompt_template: "Good {time_of_day}, {user_name}! Welcome to the Python MCP Prompt Server."
"""
            example_filepath = os.path.join(PROMPTS_DIR, "example_greeting_prompt.yaml")
            with open(example_filepath, "w", encoding='utf-8') as f:
                f.write(example_prompt_content)
            logger.info(f"已创建示例提示: '{example_filepath}'")
        except OSError as e:
            logger.error(f"无法创建提示目录 '{PROMPTS_DIR}' 或示例提示: {e}\n"
                         "请确保您有写入权限或手动创建目录。")

def initial_server_setup_and_load():
    """
    执行初始设置: 确保提示目录存在并加载初始提示。
    """
    # PROMPTS_DIR 和 SERVER_NAME 现在来自配置模块
    logger.info(f"正在初始化服务器 '{SERVER_NAME}'... 配置的提示目录: {PROMPTS_DIR}")
    _ensure_prompts_directory_exists()
    reload_all_prompts() # 这也会注册管理工具

if __name__ == "__main__":
    # SERVER_NAME 和 PROMPTS_DIR 来自配置
    logger.info(f"正在启动 {SERVER_NAME}...")
    initial_server_setup_and_load()
    
    # 安全地尝试列出当前工具
    if hasattr(mcp, 'tools') and mcp.tools is not None and hasattr(mcp.tools, 'keys'):
        try:
            current_tools = list(mcp.tools.keys())
            if current_tools:
                logger.info(f"FastMCP 服务器 '{mcp.name}' 正在运行。已注册工具 ({len(current_tools)}):")
                for tool_name in sorted(current_tools): # 排序以保证一致输出
                    logger.info(f"  - {tool_name}")
            else:
                logger.info(f"FastMCP 服务器 '{mcp.name}' 正在运行，但当前没有注册任何工具 (在初始加载后)。")
        except Exception as e:
            logger.warning(f"启动时因意外错误无法列出工具: {e}", exc_info=True)
    else:
        logger.warning(f"FastMCP 服务器 '{mcp.name}' 正在运行，但工具管理器 (mcp.tools) 在启动时不可用或不是有效的 ToolManager。无法列出工具。")
        
    logger.info(f"如果缺少工具，请检查 '{PROMPTS_DIR}' 目录中的提示文件或上面的任何错误消息。")
        
    try:
        mcp.run() # 启动 FastMCP 服务器 (默认使用 STDIO 传输)
    except Exception as e:
        logger.error(f"FastMCP 服务器运行失败: {e}", exc_info=True) # 添加 exc_info 以获取完整回溯
    finally:
        logger.info(f"{SERVER_NAME} 已停止。")

