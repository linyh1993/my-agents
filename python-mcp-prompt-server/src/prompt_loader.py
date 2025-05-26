"""
Handles loading and parsing of prompt definition files (YAML/JSON) from a directory.
"""
import os
import json
from typing import List, Dict, Any, Optional, Type
import yaml  # PyYAML

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
        print(f"Warning: Skipping invalid argument structure in '{source_filepath}': {arg_data}")
        return None

    arg_name: str = arg_data["name"]
    # Default to "string" type, normalize to lowercase for robust matching
    arg_type_str: str = arg_data.get("type", "string").lower() 
    
    python_type: Type = TYPE_MAPPING.get(arg_type_str, str)
    if arg_type_str not in TYPE_MAPPING:
        # Log if an unknown type string is encountered, but still default to 'str'
        print(f"Warning: Unknown argument type '{arg_data.get('type')}' for argument '{arg_name}' in '{source_filepath}'. Defaulting to 'string'.")

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
                    print(f"Warning: Default value '{original_default_value}' for argument '{arg_name}' in '{source_filepath}' "
                          f"could not be coerced to type '{arg_type_str}'. Default value ignored.")
                    default_value = None # Nullify if coercion failed
            except (ValueError, TypeError) as e:
                print(f"Warning: Error coercing default value '{original_default_value}' for argument '{arg_name}' in '{source_filepath}' "
                      f"to type '{arg_type_str}': {e}. Default value ignored.")
                default_value = None # Nullify on error
    
    effective_default = None
    if not is_required:
        effective_default = default_value # Use coerced (or original if valid) default value
    elif default_value is not None: # is_required is True but a default was provided
         print(f"Warning: Argument '{arg_name}' in '{source_filepath}' is required but also has a default value. "
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
        print(f"Warning: Prompt directory '{directory_path}' not found or is not a directory.")
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
                # print(f"Info: Skipping non-YAML/JSON file: '{filepath}'")
                continue 

            if not isinstance(file_content, dict): # Ensure content is a dictionary (e.g. not just a string in a YAML file)
                print(f"Warning: Content of file '{filepath}' is not a valid dictionary structure. Skipping.")
                continue
            
            # Basic structure validation for essential prompt fields
            name = file_content.get("name")
            description = file_content.get("description")
            prompt_template = file_content.get("prompt_template")

            if not (isinstance(name, str) and name and
                    isinstance(description, str) and description and
                    isinstance(prompt_template, str) and prompt_template):
                print(f"Warning: Skipping file '{filepath}' due to missing or invalid required fields. "
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
                print(f"Warning: 'arguments' field in '{filepath}' is not a list. "
                      "No arguments will be processed for this prompt.")

            prompts.append({
                "name": name,
                "description": description,
                "arguments": processed_arguments,
                "prompt_template": prompt_template,
                "source_file": filepath  # For debugging and tracking origin
            })

        except yaml.YAMLError as e:
            print(f"Warning: Error parsing YAML file '{filepath}': {e}")
        except json.JSONDecodeError as e:
            print(f"Warning: Error parsing JSON file '{filepath}': {e}")
        except Exception as e: # Catch other potential errors during file processing
            print(f"Warning: An unexpected error occurred while processing file '{filepath}': {e}")

    return prompts

if __name__ == '__main__':
    # Setup a temporary directory for example prompts for testing this module
    temp_prompts_dir_main = "prompts_temp_loader_final_review" # Unique name
    if os.path.exists(temp_prompts_dir_main):
        import shutil
        shutil.rmtree(temp_prompts_dir_main)
    os.makedirs(temp_prompts_dir_main, exist_ok=True)

    # Example: Advanced Greeter YAML (slightly modified for this test run)
    advanced_greeter_yaml_content_main = """
name: "Advanced Greeter (Final Review)"
description: "Greets with options, showcasing argument features after final review."
arguments:
  - name: "person_name"
    description: "The name of the person to greet."
    type: "string"
  - name: "greeting_style"
    description: "Style of greeting."
    type: "string"
    required: false
    default: "Cordial" # New default
  - name: "repeat_count"
    description: "Number of times to repeat the core greeting."
    type: "integer"
    required: false
    default: 1
  - name: "add_farewell"
    description: "Include a farewell message."
    type: "boolean"
    required: false
    default: true # Changed default
  - name: "measurement"
    description: "A numeric measurement."
    type: "number"
    required: false
    default: 99.9
prompt_template: |
  Greeting Style: {{greeting_style}}
  Message (x{{repeat_count}}): Hello, {{person_name}}!
  Farewell included: {{add_farewell}}
  Measurement: {{measurement}}
"""
    with open(os.path.join(temp_prompts_dir_main, "advanced_greeter_final.yaml"), "w", encoding='utf-8') as f:
        f.write(advanced_greeter_yaml_content_main)

    print(f"Final Review Loader: Loading prompts from: {temp_prompts_dir_main}")
    loaded_prompts_main = load_prompts_from_directory(temp_prompts_dir_main)
    
    print("\n--- Loaded Prompts (Final Review prompt_loader.py test) ---")
    for p_idx, prompt_detail in enumerate(loaded_prompts_main):
        print(f"\n--- Prompt {p_idx + 1} ---")
        print(f"  Name: {prompt_detail['name']}")
        print(f"  Description: {prompt_detail['description']}")
        print(f"  Source File: {prompt_detail['source_file']}")
        print(f"  Template: {prompt_detail['prompt_template'][:100].strip()}...")
        print("  Arguments:")
        if prompt_detail['arguments']:
            for arg_idx, arg_detail in enumerate(prompt_detail['arguments']):
                arg_copy = arg_detail.copy()
                arg_copy['type'] = arg_copy['type'].__name__
                print(f"    - Arg {arg_idx + 1}: {json.dumps(arg_copy)}")
        else:
            print("    (No arguments defined)")

    # print(f"\nNOTE: Test files for prompt_loader.py are in '{temp_prompts_dir_main}'.")
```
