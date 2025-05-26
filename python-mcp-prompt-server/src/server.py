"""
Main server logic for the Python MCP Prompt Server.
Handles dynamic creation and registration of MCP tools from prompt definitions,
and provides management tools for reloading prompts and listing available prompts.
"""
import os
import re
from typing import List, Dict, Any, Callable, Optional as TypingOptional # Explicit for type hints if needed elsewhere
from fastmcp import FastMCP
from src.prompt_loader import load_prompts_from_directory

# --- Constants and Global Variables ---
SERVER_NAME = "Python MCP Prompt Server"
SERVER_DESCRIPTION = "Serves prompts as MCP tools, with dynamic loading and reload capability."

# Determine project root (assuming this file, server.py, is in PROJECT_ROOT/src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Determine PROMPTS_DIR: configurable via MCP_PROMPTS_DIR environment variable.
DEFAULT_PROMPTS_PATH = os.path.join(PROJECT_ROOT, "prompts")
USER_SPECIFIED_PROMPTS_DIR = os.environ.get("MCP_PROMPTS_DIR")

if USER_SPECIFIED_PROMPTS_DIR:
    PROMPTS_DIR = os.path.abspath(USER_SPECIFIED_PROMPTS_DIR)
    print(f"INFO: Using prompts directory from MCP_PROMPTS_DIR environment variable: {PROMPTS_DIR}")
else:
    PROMPTS_DIR = os.path.abspath(DEFAULT_PROMPTS_PATH)
    print(f"INFO: MCP_PROMPTS_DIR not set. Using default prompts directory: {PROMPTS_DIR}")

# Global FastMCP instance
mcp = FastMCP(name=SERVER_NAME, description=SERVER_DESCRIPTION)

# Global dictionary to keep track of the Python functions created for each prompt tool.
# Key: Original prompt name. Value: The dynamically generated Python function object.
REGISTERED_TOOL_FUNCTIONS: Dict[str, Callable[..., Any]] = {}


# --- Helper Functions ---
def _sanitize_for_python_identifier(name: str) -> str:
    """
    Sanitizes a string to be a valid Python identifier.
    - Removes invalid characters (keeps alphanumeric and underscore).
    - Removes leading non-alphabetic characters (except underscore).
    - Prefixes with an underscore if the name starts with a digit.
    - Returns a default name if sanitization results in an empty string.
    """
    name = re.sub(r'[^0-9a-zA-Z_]', '', name) # Keep only alphanumeric and underscores
    name = re.sub(r'^[^a-zA-Z_]+', '', name)  # Remove leading chars if not letter or underscore
    
    if not name:
        return "_unnamed_prompt"
    if name[0].isdigit(): # Ensure it doesn't start with a digit
        return "_" + name
    return name


# --- Dynamic Tool Creation and Registration ---
# This section handles the dynamic generation of MCP tools from prompt definitions.
# Extensibility: To support other types of dynamically generated MCP entries (e.g., "resources"),
# a similar pattern of loading data and then creating/registering MCP objects could be followed,
# potentially with new "loader" and "creator/register" functions tailored to those types.

def _generate_dynamic_function_code(
    func_name: str,
    signature_params_str: str,
    escaped_docstring: str,
    escaped_prompt_template: str,
    format_kwargs_str: str
) -> str:
    """
    Generates the Python source code string for a dynamic prompt tool function.
    This helper centralizes the code generation template for clarity.
    """
    return f"""
def {func_name}({signature_params_str}) -> str:
    '''{escaped_docstring}'''
    # The prompt template string (as a Python string literal)
    template_str = r'{escaped_prompt_template}' # Use raw string for template
    
    # Arguments for .format() are prepared as a dictionary.
    # Keys are original argument names (from template), values are Python parameter names.
    format_args = {format_kwargs_str}
    
    # .format(**kwargs) substitutes placeholders with values from format_args.
    return template_str.format(**format_args)
"""

def create_and_register_prompt_tool(prompt_data: Dict[str, Any], mcp_instance: FastMCP):
    """
    Dynamically creates a Python function based on prompt data and registers it with FastMCP.

    Args:
        prompt_data: Dictionary with prompt definition (name, description, arguments, template).
        mcp_instance: The FastMCP instance for tool registration.
    """
    original_prompt_name = prompt_data['name']
    sanitized_func_name_base = _sanitize_for_python_identifier(original_prompt_name)
    py_func_name = f"dynamic_prompt_tool_{sanitized_func_name_base}" # Prefix for clarity

    arg_definitions_for_signature: List[str] = []
    arg_map_for_template_format: Dict[str, str] = {} # Maps template {{var}} to py_param_name

    arguments_list = prompt_data.get('arguments', [])
    if not isinstance(arguments_list, list): # Ensure 'arguments' is a list
        print(f"Warning: 'arguments' for prompt '{original_prompt_name}' is not a list. "
              "No arguments will be processed for this tool.")
        arguments_list = []

    for arg_info in arguments_list:
        original_arg_name = arg_info['name']
        py_param_name = _sanitize_for_python_identifier(original_arg_name)
        if not py_param_name: # Handle cases where sanitization might yield empty string
            print(f"Warning: Argument name '{original_arg_name}' in prompt '{original_prompt_name}' "
                  "sanitized to an empty string. Skipping this argument.")
            continue

        arg_type: type = arg_info.get('type', str) # Default to str
        is_required: bool = arg_info.get('required', True) # Default to required
        default_value: Any = arg_info.get('default', None)
        
        type_hint_str = arg_type.__name__ if hasattr(arg_type, '__name__') else "str"
        param_signature_part = f"{py_param_name}: {type_hint_str}"

        if not is_required: # Handle optional arguments and their defaults
            if default_value is not None:
                # Use repr() for default values to get their Python literal representation
                # e.g., "string" -> '"string"', True -> 'True', None -> 'None'
                param_signature_part += f" = {default_value!r}"
            else: # Optional argument without a specified default
                param_signature_part += " = None" 
        
        arg_definitions_for_signature.append(param_signature_part)
        arg_map_for_template_format[original_arg_name] = py_param_name

    signature_params_str = ", ".join(arg_definitions_for_signature)
    
    format_kwargs_items = [f"'{orig_name}': {py_name}" for orig_name, py_name in arg_map_for_template_format.items()]
    format_kwargs_str = f"{{{', '.join(format_kwargs_items)}}}"
    
    # Escape template and description for safe embedding in the generated code string.
    # Using r'' for template in generated code handles backslashes better.
    escaped_prompt_template = prompt_data['prompt_template'].replace('\\', '\\\\').replace("'", "\\'")
    escaped_docstring = prompt_data['description'].replace('\\', '\\\\').replace("'", "\\'")

    func_code = _generate_dynamic_function_code(
        py_func_name, signature_params_str, escaped_docstring,
        escaped_prompt_template, format_kwargs_str
    )
    
    # Debug: print generated code
    # print(f"--- Generated code for {py_func_name} ---\n{func_code}\n------------------------------------")
    
    # Prepare execution scope for `exec`.
    # `str`, `int`, `bool`, `float`, `None` are builtins. `List`, `Dict`, `Any` are for type hints if evaluated.
    exec_globals = {'__builtins__': __builtins__, 'List': List, 'Dict': Dict, 'Any': Any}
    local_scope: Dict[str, Any] = {}
    try:
        exec(func_code, exec_globals, local_scope)
    except Exception as e:
        print(f"ERROR: Failed to execute generated code for prompt tool '{original_prompt_name}' (function: {py_func_name}).\n"
              f"Error: {e}\nGenerated Code (inspect for issues):\n{func_code}")
        return # Skip registration if function creation failed

    created_function: TypingOptional[Callable[..., Any]] = local_scope.get(py_func_name)

    if created_function:
        REGISTERED_TOOL_FUNCTIONS[original_prompt_name] = created_function
        mcp_instance.tool(name=original_prompt_name, description=prompt_data['description'])(created_function)
        # print(f"Successfully registered tool: '{original_prompt_name}'")
    else:
        # This should be rare if exec didn't raise an error.
        print(f"ERROR: Failed to retrieve function '{py_func_name}' from exec scope for prompt '{original_prompt_name}'.")


# --- Core Server Management Tools ---
@mcp.tool(name="get_prompt_names", description="Lists the names of all currently available prompt-based tools.")
def get_prompt_names() -> List[str]:
    """
    Retrieves a list of names for all currently available prompt-based tools,
    excluding server management tools like 'reload_prompts' and 'get_prompt_names'.
    """
    if not hasattr(mcp, 'tools') or not isinstance(mcp.tools, dict):
        print("Warning: MCP tools registry not found or not a dictionary. Cannot list prompt names.")
        return []
    
    all_tool_names = list(mcp.tools.keys())
    management_tool_names = {"reload_prompts", "get_prompt_names"}
    prompt_tool_names = [name for name in all_tool_names if name not in management_tool_names]
    return prompt_tool_names

def _reregister_management_tools(mcp_instance: FastMCP):
    """Helper to re-register essential server management tools after clearing the registry."""
    mcp_instance.tool(name="reload_prompts", description="Reloads all prompt tools from the prompts directory.")(reload_all_prompts)
    mcp_instance.tool(name="get_prompt_names", description="Lists the names of all currently available prompt-based tools.")(get_prompt_names)
    # print("Re-registered essential server tools.")

@mcp.tool(name="reload_prompts", description="Reloads all prompt tools from the prompts directory.")
def reload_all_prompts() -> str:
    """
    Clears existing prompt-based tools, re-loads all prompts from PROMPTS_DIR,
    and registers them as new tools. Essential management tools are also re-registered.
    """
    global REGISTERED_TOOL_FUNCTIONS
    print(f"Reloading prompts from directory: {PROMPTS_DIR}...")
    
    if hasattr(mcp, 'tools') and isinstance(mcp.tools, dict):
        mcp.tools.clear() # Clears all tools from FastMCP's registry
        REGISTERED_TOOL_FUNCTIONS.clear() # Clear our internal tracking
    else:
        # This situation implies an issue with the FastMCP instance or its version.
        print("CRITICAL WARNING: Could not clear FastMCP tools registry. Reload may result in duplicates or errors.")

    loaded_prompts_data = load_prompts_from_directory(PROMPTS_DIR)
    
    num_registered = 0
    if not loaded_prompts_data:
        status_msg = f"Prompts directory '{PROMPTS_DIR}' is empty or contains no valid prompts. No dynamic tools loaded."
    else:
        print(f"Found {len(loaded_prompts_data)} prompt definitions to process from '{PROMPTS_DIR}'.")
        for p_data in loaded_prompts_data:
            try:
                create_and_register_prompt_tool(p_data, mcp)
                num_registered += 1
            except Exception as e: # Catch-all during the loop for safety
                prompt_name = p_data.get('name', 'Unnamed Prompt')
                print(f"ERROR: Failed to create/register tool for prompt '{prompt_name}': {e}")
        status_msg = f"Prompts reloaded. {num_registered} dynamic tools registered from '{PROMPTS_DIR}'."

    _reregister_management_tools(mcp) # Ensure management tools are always available
    print(status_msg)
    return status_msg


# --- Server Initialization and Startup ---
def _ensure_prompts_directory_exists():
    """
    Checks if PROMPTS_DIR exists, creates it if not, and adds an example prompt if newly created.
    Uses the globally configured PROMPTS_DIR.
    """
    if not os.path.exists(PROMPTS_DIR):
        print(f"Prompts directory '{PROMPTS_DIR}' not found. Creating it...")
        try:
            os.makedirs(PROMPTS_DIR)
            print(f"Successfully created prompts directory: {PROMPTS_DIR}")
            # Create an example prompt to guide the user and for initial testing.
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
prompt_template: "Good {{time_of_day}}, {{user_name}}! Welcome to the Python MCP Prompt Server."
"""
            example_filepath = os.path.join(PROMPTS_DIR, "example_greeting_prompt.yaml")
            with open(example_filepath, "w", encoding='utf-8') as f:
                f.write(example_prompt_content)
            print(f"Created an example prompt: '{example_filepath}'")
        except OSError as e:
            print(f"ERROR: Could not create prompts directory '{PROMPTS_DIR}' or example prompt: {e}\n"
                  "Please ensure you have write permissions or create the directory manually.")

def initial_server_setup_and_load():
    """
    Performs initial setup: ensures prompts directory exists and loads initial prompts.
    """
    print(f"Initializing server... Configured prompts directory: {PROMPTS_DIR}")
    _ensure_prompts_directory_exists()
    reload_all_prompts() # This also registers management tools

if __name__ == "__main__":
    print(f"Starting {SERVER_NAME}...")
    initial_server_setup_and_load()
    
    current_tools = list(mcp.tools.keys())
    if current_tools:
        print(f"FastMCP server '{mcp.name}' running. Registered tools ({len(current_tools)}):")
        for tool_name in sorted(current_tools): # Sort for consistent output
            print(f"  - {tool_name}")
    else:
        print(f"FastMCP server '{mcp.name}' running, but no tools are currently registered.")
        print(f"Please check the '{PROMPTS_DIR}' directory for prompt files or any error messages above.")
        
    try:
        mcp.run() # Start the FastMCP server (uses STDIO transport by default)
    except Exception as e:
        print(f"CRITICAL ERROR: FastMCP server failed to run: {e}")
    finally:
        print(f"{SERVER_NAME} has stopped.")

