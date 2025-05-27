"""Python MCP Prompt Server 的主要服务器逻辑。
处理从提示定义动态创建和注册 MCP 工具，并提供管理工具。
"""
import logging
import os
import sys
from typing import List, Dict, Callable

from fastmcp import FastMCP

from config_loader import load_config
from dynamic_tool_generator import create_and_register_prompt_tool
from prompt_loader import load_prompts_from_directory

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 确保 src 目录在 Python 路径中
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


class PromptServer:
    def __init__(self):
        self._prompt_functions: Dict[str, Callable] = {}
        self.prompts_dir: str = None
        self.mcp = FastMCP("Python MCP Prompt Server")
        self._setup_tools()

    def _setup_tools(self):
        """设置基本工具"""

        @self.mcp.tool()
        def get_prompt_names() -> List[str]:
            """获取所有已注册的提示工具名称"""
            return list(self._prompt_functions.keys())

        @self.mcp.tool()
        def reload_prompts() -> List[str]:
            """重新加载所有提示工具"""
            return self.load_prompts()

    def initialize(self) -> None:
        """初始化服务器"""
        # 加载配置
        config = load_config()
        if not config:
            raise ValueError("配置加载失败")

        # 设置提示目录
        self.prompts_dir = config.get("PROMPTS_DIR", os.path.join(os.path.dirname(src_dir), "prompts"))
        self._ensure_prompt_directory()

        # 加载提示工具
        self.load_prompts()

    def _ensure_prompt_directory(self) -> None:
        """确保提示目录存在"""
        if not os.path.exists(self.prompts_dir):
            os.makedirs(self.prompts_dir)
            logger.info(f"创建提示目录: {self.prompts_dir}")
        elif not os.path.isdir(self.prompts_dir):
            raise ValueError(f"提示路径 {self.prompts_dir} 不是一个目录")

    def load_prompts(self) -> List[str]:
        """加载并注册所有提示工具"""
        try:
            self._prompt_functions.clear()
            prompts = load_prompts_from_directory(self.prompts_dir)

            for prompt in prompts:
                try:
                    prompt_name = prompt.get('name', '未知')
                    prompt_function = create_and_register_prompt_tool(
                        prompt,
                        self.mcp,
                        self._prompt_functions
                    )
                    if prompt_function:
                        self._prompt_functions[prompt_name] = prompt_function
                        logger.info(f"注册提示工具: {prompt_name}")
                except Exception as e:
                    logger.error(f"注册提示工具 {prompt.get('name', '未知')} 失败: {e}")

            tool_names = list(self._prompt_functions.keys())
            logger.info(f"工具加载完成，当前工具: {', '.join(tool_names)}")
            return tool_names
        except Exception as e:
            logger.error(f"加载提示工具失败: {e}")
            return []


# 创建服务器实例
server = PromptServer()

if __name__ == "__main__":
    try:
        # 初始化服务器
        server.initialize()

        # 显示服务器状态
        logger.info("=== Python MCP Prompt Server 启动成功 ===")
        logger.info(f"提示目录: {server.prompts_dir}")

        # 运行服务器
        server.mcp.run()
    except KeyboardInterrupt:
        logger.info("正在关闭服务器...")
    except Exception as e:
        logger.error(f"服务器运行时出错: {e}")
        sys.exit(1)
