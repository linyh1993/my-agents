"""
处理从目录加载和解析提示定义文件 (YAML/JSON)。
"""
import os
import json
from typing import List, Dict, Any, Optional, Type
import yaml  # PyYAML
import logging

# 获取一个 logger 实例
logger = logging.getLogger(__name__)

# 从 YAML/JSON 字符串到 Python 类型对象的类型映射
TYPE_MAPPING: Dict[str, Type] = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": float,  # 'number' 在 JSON schema 和 YAML 中通常映射到 float
}

def _parse_prompt_argument(arg_data: Dict[str, Any], source_filepath: str) -> Optional[Dict[str, Any]]:
    """
    解析提示定义中的单个参数字典。

    Args:
        arg_data: 代表参数的字典。
        source_filepath: 提示文件的路径，用于日志/警告。

    Returns:
        包含处理后参数详情的字典，如果验证失败则为 None。
    """
    if not isinstance(arg_data, dict) or "name" not in arg_data:
        logger.warning(f"在 '{source_filepath}' 中跳过无效的参数结构: {arg_data}")
        return None

    arg_name: str = arg_data["name"]
    # 默认为 "string" 类型，规范化为小写以便稳健匹配
    arg_type_str: str = arg_data.get("type", "string").lower() 
    
    python_type: Type = TYPE_MAPPING.get(arg_type_str, str)
    if arg_type_str not in TYPE_MAPPING:
        # 如果遇到未知类型字符串，则记录日志，但仍默认为 'str'
        logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中的未知参数类型 '{arg_data.get('type')}'。默认为 'string'。")

    is_required: bool = arg_data.get("required", True) # 参数默认是必需的
    default_value: Any = arg_data.get("default", None)

    # 如有必要，验证和强制转换 default_value，尤其是在非必需的情况下
    if default_value is not None and not is_required: # 默认值主要适用于非必需参数
        if not isinstance(default_value, python_type):
            original_default_value = default_value
            try:
                # 尝试常见的强制转换 (例如，字符串 "true" 转为布尔值 True)
                if python_type is bool and isinstance(default_value, str):
                    default_value = default_value.lower() in ['true', 'yes', '1', 'on']
                elif python_type in [int, float] and isinstance(default_value, (str, int, float)):
                    default_value = python_type(default_value)
                # 如果出现其他模式，在此处添加更多特定的强制转换
                
                if not isinstance(default_value, python_type): # 尝试强制转换后重新检查
                    logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中的默认值 '{original_default_value}' "
                                   f"无法强制转换为类型 '{arg_type_str}'。默认值将被忽略。")
                    default_value = None # 如果强制转换失败，则置为 None
            except (ValueError, TypeError) as e:
                logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中强制转换默认值 '{original_default_value}' "
                               f"为类型 '{arg_type_str}' 时出错: {e}。默认值将被忽略。")
                default_value = None # 出错时置为 None
    
    effective_default = None
    if not is_required:
        effective_default = default_value # 使用强制转换后的 (或有效的原始) 默认值
    elif default_value is not None: # is_required 为 True 但提供了默认值
         logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中是必需的，但也设置了默认值。"
                        "由于参数是强制性的，默认值将被忽略。")
         # effective_default 对必需参数保持为 None

    return {
        "name": arg_name,
        "description": arg_data.get("description", ""), # 可选的描述
        "type": python_type,
        "required": is_required,
        "default": effective_default,
    }

def load_prompts_from_directory(directory_path: str) -> List[Dict[str, Any]]:
    """
    扫描目录中的提示文件 (YAML/JSON)，解析其内容，
    并返回一个结构化的提示字典列表。

    每个提示字典包括其名称、描述、处理后的参数、
    提示模板字符串和源文件路径。

    Args:
        directory_path: 包含提示文件的目录路径。

    Returns:
        一个字典列表，其中每个字典代表一个有效的提示。
        如果目录未找到或不包含有效提示，则返回空列表。
    """
    prompts: List[Dict[str, Any]] = []
    if not os.path.isdir(directory_path):
        logger.warning(f"提示目录 '{directory_path}' 未找到或不是一个目录。")
        return prompts

    for filename in os.listdir(directory_path):
        filepath = os.path.join(directory_path, filename)
        if not os.path.isfile(filepath): # 跳过子目录或其他非文件条目
            continue

        file_content: Optional[Any] = None
        try:
            # 可扩展性: 要添加对其他文件类型 (例如 TOML) 的支持，
            # 在此处添加另一个 'elif' 块，检查新的文件扩展名
            # 并使用其各自的解析器。
            if filename.endswith((".yaml", ".yml")):
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_content = yaml.safe_load(f)
            elif filename.endswith(".json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_content = json.load(f)
            else:
                # 静默跳过与预期扩展名不匹配的文件，或在需要详细调试时记录日志。
                # logger.info(f"跳过非 YAML/JSON 文件: '{filepath}'")
                continue 

            if not isinstance(file_content, dict): # 确保内容是一个字典 (例如，不是 YAML 文件中的纯字符串)
                logger.warning(f"文件 '{filepath}' 的内容不是有效的字典结构。正在跳过。")
                continue
            
            # 基本结构验证，检查必要的提示字段
            name = file_content.get("name")
            description = file_content.get("description")
            prompt_template = file_content.get("prompt_template")

            if not (isinstance(name, str) and name and
                    isinstance(description, str) and description and
                    isinstance(prompt_template, str) and prompt_template):
                logger.warning(f"因缺少或无效的必需字段而跳过文件 '{filepath}'。"
                               "'name', 'description', 和 'prompt_template' 必须是非空字符串。")
                continue

            # 处理参数列表
            arguments_data: List[Dict[str, Any]] = file_content.get("arguments", []) # 默认为空列表
            processed_arguments: List[Dict[str, Any]] = []
            if isinstance(arguments_data, list):
                for arg_data_item in arguments_data:
                    parsed_arg = _parse_prompt_argument(arg_data_item, filepath)
                    if parsed_arg:
                        processed_arguments.append(parsed_arg)
            elif arguments_data is not None: # 如果 'arguments' 存在但不是列表
                logger.warning(f"'{filepath}' 中的 'arguments' 字段不是列表。"
                               "此提示将不处理任何参数。")

            prompts.append({
                "name": name,
                "description": description,
                "arguments": processed_arguments,
                "prompt_template": prompt_template,
                "source_file": filepath  # 用于调试和跟踪来源
            })

        except yaml.YAMLError as e:
            logger.warning(f"解析 YAML 文件 '{filepath}' 时出错: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"解析 JSON 文件 '{filepath}' 时出错: {e}")
        except Exception as e: # 捕获文件处理期间其他可能的错误
            logger.warning(f"处理文件 '{filepath}' 时发生意外错误: {e}")

    return prompts
