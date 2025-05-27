import json
import logging
import os
from typing import List, Dict, Any, Optional, Type

import yaml

logger = logging.getLogger(__name__)

TYPE_MAPPING: Dict[str, Type] = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": float
}


def _parse_prompt_argument(arg_data: Dict[str, Any], source_filepath: str) -> Optional[Dict[str, Any]]:
    """解析提示定义中的单个参数字典。"""
    if not isinstance(arg_data, dict) or "name" not in arg_data:
        logger.warning(f"在 '{source_filepath}' 中跳过无效的参数结构: {arg_data}")
        return None

    arg_name: str = arg_data["name"]
    arg_type_str: str = arg_data.get("type", "string").lower()
    python_type: Type = TYPE_MAPPING.get(arg_type_str, str)
    is_required: bool = arg_data.get("required", True)
    default_value: Any = arg_data.get("default", None)

    if arg_type_str not in TYPE_MAPPING:
        logger.warning(
            f"参数 '{arg_name}' 在 '{source_filepath}' 中使用未知类型 '{arg_data.get('type')}'，默认使用 'string'")

    if default_value is not None:
        if is_required:
            logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中是必需的，默认值将被忽略")
            default_value = None
        elif not isinstance(default_value, python_type):
            try:
                if python_type is bool and isinstance(default_value, str):
                    default_value = default_value.lower() in ['true', 'yes', '1', 'on']
                elif python_type in (int, float) and isinstance(default_value, (str, int, float)):
                    default_value = python_type(default_value)

                if not isinstance(default_value, python_type):
                    logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中的默认值类型转换失败，将被忽略")
                    default_value = None
            except (ValueError, TypeError):
                logger.warning(f"参数 '{arg_name}' 在 '{source_filepath}' 中的默认值类型转换失败，将被忽略")
                default_value = None

    return {
        "name": arg_name,
        "description": arg_data.get("description", ""),
        "type": python_type,
        "required": is_required,
        "default": default_value
    }


def load_prompts_from_directory(directory_path: str) -> List[Dict[str, Any]]:
    """扫描目录中的提示文件并返回结构化的提示字典列表。"""
    prompts: List[Dict[str, Any]] = []
    if not os.path.isdir(directory_path):
        logger.warning(f"提示目录 '{directory_path}' 未找到或不是一个目录")
        return prompts

    for filename in os.listdir(directory_path):
        filepath = os.path.join(directory_path, filename)
        if not os.path.isfile(filepath):
            continue

        try:
            file_content = None
            if filename.endswith((".yaml", ".yml")):
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_content = yaml.safe_load(f)
            elif filename.endswith(".json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_content = json.load(f)
            else:
                continue

            if not isinstance(file_content, dict):
                logger.warning(f"文件 '{filepath}' 的内容不是有效的字典结构，已跳过")
                continue

            required_fields = ["name", "description", "prompt_template"]
            if not all(
                    isinstance(file_content.get(field), str) and file_content.get(field) for field in required_fields):
                logger.warning(f"文件 '{filepath}' 缺少必需字段或字段值无效，已跳过")
                continue

            arguments_data = file_content.get("arguments", [])
            processed_arguments = []
            if isinstance(arguments_data, list):
                processed_arguments = [arg for arg_item in arguments_data
                                       if (arg := _parse_prompt_argument(arg_item, filepath))]
            else:
                logger.warning(f"'{filepath}' 中的 'arguments' 字段不是列表，将忽略参数处理")

            prompts.append({
                "name": file_content["name"],
                "description": file_content["description"],
                "arguments": processed_arguments,
                "prompt_template": file_content["prompt_template"],
                "source_file": filepath
            })

        except (yaml.YAMLError, json.JSONDecodeError) as e:
            logger.warning(f"解析文件 '{filepath}' 时出错: {e}")
        except Exception as e:
            logger.warning(f"处理文件 '{filepath}' 时发生意外错误: {e}")

    return prompts
