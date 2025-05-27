"""
Handles loading and parsing of prompt definition files (YAML/JSON) from a directory.
"""
import os
import json
from typing import List, Dict, Any, Optional, Type
import yaml  # PyYAML
import logging

# Get a logger instance
logger = logging.getLogger(__name__)

# Type mapping from YAML/JSON string to Python type object
TYPE_MAPPING: Dict[str, Type] = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "number": float,  # 'number' typically maps to float in JSON schema and YAML
}

def _parse_prompt_argument(arg_data: Dict[str, Any], source_filepath: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single argument dictionary from a prompt definition.

    Args:
        arg_data: The dictionary representing the argument.
        source_filepath: The path to the prompt file, for logging/warnings.

    Returns:
        A dictionary with processed argument details, or None if validation fails.
    """
    if not isinstance(arg_data, dict) or "name" not in arg_data:
        logger.warning(f"Skipping invalid argument structure in '{source_filepath}': {arg_data}")
        return None

    arg_name: str = arg_data["name"]
    # Default to "string" type, normalize to lowercase for robust matching
    arg_type_str: str = arg_data.get("type", "string").lower() 
    
    python_type: Type = TYPE_MAPPING.get(arg_type_str, str)
    if arg_type_str not in TYPE_MAPPING:
        # Log if an unknown type string is encountered, but still default to 'str'
        logger.warning(f"Unknown argument type '{arg_data.get('type')}' for argument '{arg_name}' in '{source_filepath}'. Defaulting to 'string'.")

    is_required: bool = arg_data.get("required", True) # Arguments are required by default
    default_value: Any = arg_data.get("default", None)

    # Validate and coerce default_value if necessary, especially if not required
    if default_value is not None and not is_required: # Default values primarily apply to non-required args
        if not isinstance(default_value, python_type):
            original_default_value = default_value
            try:
                # Attempt common coercions (e.g., string "true" to bool True)
                if python_type is bool and isinstance(default_value, str):
                    default_value = default_value.lower() in ['true', 'yes', '1', 'on']
                elif python_type in [int, float] and isinstance(default_value, (str, int, float)):
                    default_value = python_type(default_value)
                # Add more specific coercions here if other patterns emerge
                
                if not isinstance(default_value, python_type): # Re-check after attempted coercion
                    logger.warning(f"Default value '{original_default_value}' for argument '{arg_name}' in '{source_filepath}' "
                                   f"could not be coerced to type '{arg_type_str}'. Default value ignored.")
                    default_value = None # Nullify if coercion failed
            except (ValueError, TypeError) as e:
                logger.warning(f"Error coercing default value '{original_default_value}' for argument '{arg_name}' in '{source_filepath}' "
                               f"to type '{arg_type_str}': {e}. Default value ignored.")
                default_value = None # Nullify on error
    
    effective_default = None
    if not is_required:
        effective_default = default_value # Use coerced (or original if valid) default value
    elif default_value is not None: # is_required is True but a default was provided
         logger.warning(f"Argument '{arg_name}' in '{source_filepath}' is required but also has a default value. "
                        "The default value will be ignored as the argument is mandatory.")
         # effective_default remains None for required arguments

    return {
        "name": arg_name,
        "description": arg_data.get("description", ""), # Optional description
        "type": python_type,
        "required": is_required,
        "default": effective_default,
    }

def load_prompts_from_directory(directory_path: str) -> List[Dict[str, Any]]:
    """
    Scans a directory for prompt files (YAML/JSON), parses their content,
    and returns a list of structured prompt dictionaries.

    Each prompt dictionary includes its name, description, processed arguments,
    the prompt template string, and the source file path.

    Args:
        directory_path: The path to the directory containing prompt files.

    Returns:
        A list of dictionaries, where each dictionary represents a valid prompt.
        Returns an empty list if the directory is not found or contains no valid prompts.
    """
    prompts: List[Dict[str, Any]] = []
    if not os.path.isdir(directory_path):
        logger.warning(f"Prompt directory '{directory_path}' not found or is not a directory.")
        return prompts

    for filename in os.listdir(directory_path):
        filepath = os.path.join(directory_path, filename)
        if not os.path.isfile(filepath): # Skip subdirectories or other non-file entries
            continue

        file_content: Optional[Any] = None
        try:
            # Extensibility: To add support for other file types (e.g., TOML),
            # add another 'elif' block here checking for the new file extension
            # and using its respective parser.
            if filename.endswith((".yaml", ".yml")):
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_content = yaml.safe_load(f)
            elif filename.endswith(".json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    file_content = json.load(f)
            else:
                # Silently skip files not matching expected extensions, or log if verbose debugging is needed.
                # logger.info(f"Skipping non-YAML/JSON file: '{filepath}'")
                continue 

            if not isinstance(file_content, dict): # Ensure content is a dictionary (e.g. not just a string in a YAML file)
                logger.warning(f"Content of file '{filepath}' is not a valid dictionary structure. Skipping.")
                continue
            
            # Basic structure validation for essential prompt fields
            name = file_content.get("name")
            description = file_content.get("description")
            prompt_template = file_content.get("prompt_template")

            if not (isinstance(name, str) and name and
                    isinstance(description, str) and description and
                    isinstance(prompt_template, str) and prompt_template):
                logger.warning(f"Skipping file '{filepath}' due to missing or invalid required fields. "
                               "'name', 'description', and 'prompt_template' must be non-empty strings.")
                continue

            # Process arguments list
            arguments_data: List[Dict[str, Any]] = file_content.get("arguments", []) # Default to empty list
            processed_arguments: List[Dict[str, Any]] = []
            if isinstance(arguments_data, list):
                for arg_data_item in arguments_data:
                    parsed_arg = _parse_prompt_argument(arg_data_item, filepath)
                    if parsed_arg:
                        processed_arguments.append(parsed_arg)
            elif arguments_data is not None: # If 'arguments' exists but is not a list
                logger.warning(f"'arguments' field in '{filepath}' is not a list. "
                               "No arguments will be processed for this prompt.")

            prompts.append({
                "name": name,
                "description": description,
                "arguments": processed_arguments,
                "prompt_template": prompt_template,
                "source_file": filepath  # For debugging and tracking origin
            })

        except yaml.YAMLError as e:
            logger.warning(f"Error parsing YAML file '{filepath}': {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"Error parsing JSON file '{filepath}': {e}")
        except Exception as e: # Catch other potential errors during file processing
            logger.warning(f"An unexpected error occurred while processing file '{filepath}': {e}")

    return prompts
