import logging
import re
from typing import List, Dict, Any, Callable, Optional, Tuple

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


def _sanitize_for_python_identifier(name: str) -> str:
    """将字符串转换为有效的Python标识符"""
    name = re.sub(r'[^0-9a-zA-Z_]', '', name)
    name = re.sub(r'^[^a-zA-Z_]+', '', name)
    return "_unnamed_prompt" if not name else f"_{name}" if name[0].isdigit() else name


def _prepare_function_parameters(
        arguments_list: List[Dict[str, Any]],
        original_prompt_name: str
) -> Tuple[List[str], Dict[str, str]]:
    """准备函数签名参数和模板格式化映射"""
    if not isinstance(arguments_list, list):
        logger.warning(f"提示'{original_prompt_name}'的参数定义无效")
        return [], {}

    arg_definitions = []
    arg_map = {}

    for arg in arguments_list:
        try:
            name = arg['name']
            py_name = _sanitize_for_python_identifier(name)
            if not py_name:
                logger.warning(f"提示'{original_prompt_name}'的参数'{name}'无效")
                continue

            arg_type = arg.get('type', str)
            type_name = getattr(arg_type, '__name__', 'str')
            is_required = arg.get('required', True)
            default = arg.get('default')

            param_def = f"{py_name}: {type_name}"
            if not is_required:
                param_def += f" = {default!r}" if default is not None else " = None"

            arg_definitions.append(param_def)
            arg_map[name] = f"{py_name}"
        except KeyError as e:
            logger.error(f"提示'{original_prompt_name}'的参数定义缺少必要字段: {e}")
            continue

    return arg_definitions, arg_map


def _generate_dynamic_function_code(
        func_name: str,
        params_str: str,
        docstring: str,
        template: str,
        kwargs_str: str
) -> str:
    """
生成动态函数代码
    """
    return f"""
def {func_name}({params_str}) -> str:
    '''{docstring}'''
    template_str = r'''{template}'''
    format_args = {{{kwargs_str}}}
    return template_str.format(**format_args)
"""


def create_and_register_prompt_tool(
        prompt_data: Dict[str, Any],
        mcp_instance: FastMCP,
        registered_tool_functions_dict: Dict[str, Callable]
) -> Optional[Callable]:
    """动态创建并注册提示工具函数"""
    try:
        name = prompt_data['name']
        py_func_name = f"dynamic_prompt_tool_{_sanitize_for_python_identifier(name)}"

        arg_defs, arg_map = _prepare_function_parameters(prompt_data.get('arguments', []), name)
        params_str = ", ".join(arg_defs)
        kwargs_str = ", ".join(f"'{k}': {v}" for k, v in arg_map.items())

        template = prompt_data['prompt_template'].replace('\\', '\\\\').replace("'", "\\'")
        docstring = prompt_data['description'].replace('\\', '\\\\').replace("'", "\\'")

        func_code = _generate_dynamic_function_code(py_func_name, params_str, docstring, template, kwargs_str)

        logger.info(f"生成的代码: {func_code}")

        namespace = {'__builtins__': __builtins__}
        try:
            exec(func_code, namespace)
        except Exception as e:
            logger.error(f"提示工具'{name}'代码执行失败: {e}")
            return None

        func = namespace.get(py_func_name)
        if not func:
            logger.error(f"提示工具'{name}'函数创建失败")
            return None

        # 先注册到 MCP 实例
        decorated_func = mcp_instance.tool(name=name, description=docstring)(func)
        # 再添加到函数字典
        registered_tool_functions_dict[name] = decorated_func
        return decorated_func

    except KeyError as e:
        logger.error(f"提示工具创建失败: 缺少必要字段 {e}")
        return None
    except Exception as e:
        logger.error(f"提示工具创建过程出现未知错误: {e}")
        return None
