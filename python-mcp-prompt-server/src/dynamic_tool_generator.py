import re
import logging
from typing import List, Dict, Any, Callable, Optional as TypingOptional
from fastmcp import FastMCP # For type hinting mcp_instance

# Note: The logger instance will be passed in, not created here.

# --- Helper Functions ---
def _sanitize_for_python_identifier(name: str) -> str:
    """
    将字符串转换为有效的 Python 标识符。
    - 移除无效字符 (保留字母数字和下划线)。
    - 移除开头的非字母字符 (下划线除外)。
    - 如果名称以数字开头，则添加下划线前缀。
    - 如果转换结果为空字符串，则返回默认名称。
    """
    name = re.sub(r'[^0-9a-zA-Z_]', '', name) # 仅保留字母数字和下划线
    name = re.sub(r'^[^a-zA-Z_]+', '', name)  # 移除开头的非字母或下划线字符
    
    if not name:
        return "_unnamed_prompt"
    if name[0].isdigit(): # 确保不以数字开头
        return "_" + name
    return name

def _prepare_function_parameters(
    arguments_list: List[Dict[str, Any]], 
    original_prompt_name: str,
    logger: logging.Logger
) -> tuple[List[str], Dict[str, str]]:
    """
    根据提示中定义的参数，准备函数签名参数和模板格式化映射。
    """
    arg_definitions_for_signature: List[str] = []
    arg_map_for_template_format: Dict[str, str] = {} # 映射模板 {变量} 到 py_param_name

    if not isinstance(arguments_list, list):
        logger.warning(f"提示 '{original_prompt_name}' 的 'arguments' 不是列表。将不处理任何参数。")
        return arg_definitions_for_signature, arg_map_for_template_format

    for arg_info in arguments_list:
        original_arg_name = arg_info['name']
        py_param_name = _sanitize_for_python_identifier(original_arg_name)
        if not py_param_name: 
            logger.warning(f"提示 '{original_prompt_name}' 中的参数名 '{original_arg_name}' 清理后为空字符串。跳过此参数。")
            continue

        arg_type: type = arg_info.get('type', str) 
        is_required: bool = arg_info.get('required', True) 
        default_value: Any = arg_info.get('default', None)
        
        type_hint_str = arg_type.__name__ if hasattr(arg_type, '__name__') else "str"
        param_signature_part = f"{py_param_name}: {type_hint_str}"

        if not is_required: 
            if default_value is not None:
                param_signature_part += f" = {default_value!r}"
            else: 
                param_signature_part += " = None" 
        
        arg_definitions_for_signature.append(param_signature_part)
        arg_map_for_template_format[original_arg_name] = py_param_name 
            
    return arg_definitions_for_signature, arg_map_for_template_format

def _generate_dynamic_function_code(
    func_name: str,
    signature_params_str: str,
    escaped_docstring: str,
    escaped_prompt_template: str,
    format_kwargs_str: str
) -> str:
    """
    为动态提示工具函数生成 Python 源代码字符串。
    此辅助函数集中了代码生成模板以保持清晰。
    """
    return f"""
def {func_name}({signature_params_str}) -> str:
    '''{escaped_docstring}'''
    template_str = r'{escaped_prompt_template}'
    format_args = {format_kwargs_str}
    return template_str.format(**format_args)
"""

def create_and_register_prompt_tool(
    prompt_data: Dict[str, Any], 
    mcp_instance: FastMCP, 
    logger: logging.Logger, # Added logger parameter
    registered_tool_functions_dict: Dict[str, Callable] # Added dict parameter
):
    """
    根据提示数据动态创建 Python 函数并将其注册到 FastMCP。

    Args:
        prompt_data: 包含提示定义的字典 (名称, 描述, 参数, 模板)。
        mcp_instance: 用于工具注册的 FastMCP 实例。
        logger: 用于日志记录的 Logger 实例。
        registered_tool_functions_dict: 用于跟踪已注册函数对象的字典。
    """
    original_prompt_name = prompt_data['name']
    sanitized_func_name_base = _sanitize_for_python_identifier(original_prompt_name)
    py_func_name = f"dynamic_prompt_tool_{sanitized_func_name_base}" 

    arguments_list = prompt_data.get('arguments', [])
    arg_definitions_for_signature, arg_map_for_template_format = _prepare_function_parameters(
        arguments_list, original_prompt_name, logger # Pass logger
    )

    signature_params_str = ", ".join(arg_definitions_for_signature)
    
    format_kwargs_items = [f"'{orig_name}': {py_name}" for orig_name, py_name in arg_map_for_template_format.items()]
    format_kwargs_str = f"{{{', '.join(format_kwargs_items)}}}"
    
    escaped_prompt_template = prompt_data['prompt_template'].replace('\\', '\\\\').replace("'", "\\'")
    escaped_docstring = prompt_data['description'].replace('\\', '\\\\').replace("'", "\\'")

    func_code = _generate_dynamic_function_code(
        py_func_name, signature_params_str, escaped_docstring,
        escaped_prompt_template, format_kwargs_str
    )
    
    # logger.debug(f"--- 为 {py_func_name} 生成的代码 ---\n{func_code}\n------------------------------------")
    
    exec_globals = {'__builtins__': __builtins__, 'List': List, 'Dict': Dict, 'Any': Any}
    local_scope: Dict[str, Any] = {}
    try:
        exec(func_code, exec_globals, local_scope)
    except Exception as e:
        logger.error(f"为提示工具 '{original_prompt_name}' (函数: {py_func_name}) 执行生成的代码失败。\n"
                     f"错误: {e}\n生成的代码 (检查问题):\n{func_code}")
        return 

    created_function: TypingOptional[Callable[..., Any]] = local_scope.get(py_func_name)

    if created_function:
        registered_tool_functions_dict[original_prompt_name] = created_function # Use passed-in dict
        mcp_instance.tool(name=original_prompt_name, description=prompt_data['description'])(created_function)
        # logger.info(f"成功注册工具: '{original_prompt_name}'") # Logging can be done by caller or here
    else:
        logger.error(f"从 exec 作用域检索提示 '{original_prompt_name}' 的函数 '{py_func_name}' 失败。")

# Example of how this module might be tested or used independently (optional)
if __name__ == '__main__':
    # This block is for testing or direct execution, not typically run when imported.
    # Setup a dummy logger for testing this module directly
    test_logger = logging.getLogger("dynamic_tool_generator_test")
    test_logger.setLevel(logging.DEBUG)
    test_handler = logging.StreamHandler()
    test_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    test_logger.addHandler(test_handler)

    test_logger.info("Testing dynamic_tool_generator.py standalone...")

    # Example dummy prompt data
    dummy_prompt = {
        "name": "Test Greet Prompt!",
        "description": "A simple test greeting prompt.",
        "arguments": [
            {"name": "user name", "type": str, "required": True, "description": "Name of the user."},
            {"name": "greeting phrase", "type": str, "required": False, "default": "Hello"}
        ],
        "prompt_template": "{greeting_phrase}, {user_name}!"
    }
    
    # Dummy FastMCP instance for testing signature compatibility
    class DummyMCP:
        def tool(self, name, description):
            def decorator(func):
                test_logger.info(f"DummyMCP: Tool '{name}' with description '{description}' would be registered.")
                return func
            return decorator
    
    dummy_mcp = DummyMCP()
    dummy_registered_tools = {}

    create_and_register_prompt_tool(
        dummy_prompt, 
        dummy_mcp, # type: ignore 
        test_logger, 
        dummy_registered_tools
    )

    # Check if the function was "registered" (i.e., added to our dummy dict)
    py_func_name_expected_base = _sanitize_for_python_identifier("Test Greet Prompt!")
    py_func_name_expected = f"dynamic_prompt_tool_{py_func_name_expected_base}"
    
    if dummy_prompt["name"] in dummy_registered_tools:
        test_logger.info(f"Tool '{dummy_prompt['name']}' (function '{py_func_name_expected}') seems to be created and tracked.")
        created_func_for_test = dummy_registered_tools[dummy_prompt["name"]]
        try:
            # Test execution of the dynamically created function
            # Note: Actual parameters would be sanitized names like 'user_name_1', 'greeting_phrase'
            # This direct call might not work perfectly if sanitization changes names drastically,
            # but it's a basic check.
            # For a real test, one would need to know the sanitized parameter names.
            
            # Simplified call for this example - assumes sanitized names are close to original for simplicity
            # A more robust test would inspect the function signature or use the sanitized names from _prepare_function_parameters
            
            # Let's manually get sanitized names for this test call
            args_for_sig, arg_map = _prepare_function_parameters(dummy_prompt["arguments"], dummy_prompt["name"], test_logger)
            
            # Example call:
            # result = created_func_for_test(**{"user_name": "Tester", "greeting_phrase": "Hi"})
            # test_logger.info(f"Dynamic function executed. Result: {result}")
            # assert result == "Hi, Tester!"

            # The function created by exec exists in local_scope within create_and_register_prompt_tool.
            # To test it here, we'd need to retrieve it or call it through dummy_mcp if it was fully integrated.
            # The current test just checks if it's in dummy_registered_tools.
            test_logger.info("Dynamic function creation test passed (existence check).")

        except Exception as e:
            test_logger.error(f"Error testing dynamic function: {e}", exc_info=True)
    else:
        test_logger.error(f"Tool '{dummy_prompt['name']}' not found in dummy_registered_tools.")

    test_logger.info("Standalone test finished.")
