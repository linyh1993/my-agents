# Python MCP Prompt Server

## Introduction/Overview

The Python MCP Prompt Server is a Python-based implementation of a Machine-Code Protocol (MCP) server designed for managing and serving prompt templates. It allows users to define a collection of prompts in simple YAML or JSON files, which are then dynamically exposed as callable tools by an MCP client (such as Cursor, Raycast, Windsurf, etc.).

This project is inspired by the original `mcp-prompt-server` and leverages the `fastmcp` library for handling MCP communication. Its key features include dynamic loading of prompts, hot reloading of prompt definitions without server restart, and easy extensibility.

## Features

*   **Dynamic Prompt Loading:** Loads prompt definitions from YAML and JSON files located in a specified directory.
*   **Dynamic Tool Generation:** Automatically generates MCP tools for each loaded prompt.
*   **Hot Reloading:** Includes a `reload_prompts` tool that allows clients to refresh the available prompts without restarting the server. This is useful when adding, removing, or modifying prompt files.
*   **Prompt Discovery:** Provides a `get_prompt_names` tool to list all currently available prompt-based tools.
*   **Typed Arguments:** Supports type hints (string, integer, boolean, number) and default values for prompt arguments.
*   **Easy to Define Prompts:** Uses a simple and clear structure for prompt definition files.
*   **MCP Compatible:** Built using `fastmcp`, making it compatible with various MCP clients.
*   **Customizable:** The prompt directory and server behavior can be adjusted.
*   **Configurable Prompts Directory:** The directory from which prompts are loaded can be configured via an environment variable.

## Prerequisites

*   Python 3.8+ (or a version compatible with `fastmcp`)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/python-mcp-prompt-server.git # Replace with actual URL if available
    cd python-mcp-prompt-server
    ```

2.  **Set up a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Directory Structure

```
python-mcp-prompt-server/
├── prompts/            # Default directory for your YAML/JSON prompt definition files.
│                       # Can be overridden by the MCP_PROMPTS_DIR environment variable.
├── src/                # Source code for the server.
│   ├── server.py       # Main server logic, MCP tool registration.
│   └── prompt_loader.py # Logic for loading and parsing prompt files.
├── tests/              # Unit and integration tests.
│   ├── test_prompt_loader.py
│   └── test_server.py
├── requirements.txt    # Python package dependencies.
└── README.md           # This file.
```

## Configuration

### Prompts Directory

The directory from which the server loads prompt definition files can be configured using the `MCP_PROMPTS_DIR` environment variable.

*   **If `MCP_PROMPTS_DIR` is set:** The server will use the path specified in this environment variable. The path will be resolved to an absolute path. If you provide a relative path, it will be resolved relative to the current working directory from which the server is launched.
*   **If `MCP_PROMPTS_DIR` is not set:** The server defaults to using the `prompts/` directory located at the root of the project.

**Example:**
To run the server with prompts from `/home/user/my_custom_prompts`:
```bash
MCP_PROMPTS_DIR="/home/user/my_custom_prompts" python src/server.py
```
Or, if using a relative path (e.g., a directory named `custom_prompts` at the same level as `python-mcp-prompt-server`):
```bash
MCP_PROMPTS_DIR="../custom_prompts" python src/server.py 
# (Assuming you are running from within the python-mcp-prompt-server directory)
```

## Defining Prompts

Prompts are defined in `.yaml` or `.json` files placed in the configured prompts directory (see "Configuration" section above). Each file should define a single prompt.

**Prompt File Structure:**

*   `name` (string, required): The name of the prompt, which will also be the MCP tool name.
*   `description` (string, required): A description of what the prompt does. This will be the MCP tool description.
*   `arguments` (list, optional): A list of argument objects that the prompt template expects.
    *   Each argument object has the following fields:
        *   `name` (string, required): The name of the argument (used as `{{argument_name}}` in the template).
        *   `description` (string, optional): A description of the argument.
        *   `type` (string, optional, default: `"string"`): The type of the argument. Supported types:
            *   `"string"`: A text string.
            *   `"integer"`: An integer number.
            *   `"boolean"`: A boolean value (true/false).
            *   `"number"`: A floating-point number.
        *   `required` (boolean, optional, default: `true`): Whether the argument is required.
        *   `default` (any, optional): A default value for the argument if it's not `required` and no value is provided by the client. The type of the default value should match the specified `type`.
*   `prompt_template` (string, required): The template string for the prompt. Use `{{argument_name}}` placeholders for arguments.

**Example 1: Simple Echo Prompt (`prompts/echo.yaml`)**

```yaml
name: "Echo Text"
description: "Echoes back the provided text."
arguments:
  - name: "text_to_echo"
    description: "The text that should be echoed back."
    type: "string"
    required: true
prompt_template: "You said: {{text_to_echo}}"
```

**Example 2: Advanced Greeter (`prompts/advanced_greeter.yaml`)**

```yaml
name: "Advanced Greeter"
description: "Greets a person with configurable options."
arguments:
  - name: "person_name"
    description: "The name of the person to greet."
    type: "string"
  - name: "greeting_phrase"
    description: "The phrase to use for the greeting (e.g., Hello, Hi, Yo)."
    type: "string"
    required: false
    default: "Hello"
  - name: "enthusiasm_level"
    description: "Level of enthusiasm from 1 (calm) to 5 (very excited)."
    type: "integer"
    required: false
    default: 3
  - name: "formal_greeting"
    description: "Use a formal greeting style (true/false)."
    type: "boolean"
    required: false
    default: false
prompt_template: |
  {{greeting_phrase}}, {{person_name}}!
  Enthusiasm: {{enthusiasm_level}}/5.
  Formal: {{formal_greeting}}.
  Have a great day!
```

## Running the Server

To run the server, navigate to the project's root directory and execute:

```bash
python src/server.py
```
Remember to set the `MCP_PROMPTS_DIR` environment variable if you want to use a custom prompts directory (see "Configuration" section).

By default, the server uses STDIO (`stdin`/`stdout`) for MCP communication, which is common for local client integrations.

## Using the Server (Client Configuration)

You can connect various MCP clients to this server. Here are a few examples:

**Cursor:**

1.  Open Cursor's settings (e.g., `settings.json` or via the UI if available).
2.  Add or modify the `servers` array:

    ```json
    {
      "servers": [
        {
          "name": "Python Prompt Server",
          "command": "python", // Or absolute path to python in your .venv
          "args": [
            "/path/to/your/python-mcp-prompt-server/src/server.py" // Absolute path to server.py
          ],
          // If using MCP_PROMPTS_DIR, you might need to set it in the environment
          // where Cursor launches this command, or adjust the command itself if your shell allows.
          // For example, on Linux/macOS, you might try:
          // "command": "bash",
          // "args": [
          //   "-c",
          //   "MCP_PROMPTS_DIR=/custom/prompts/path /path/to/venv/bin/python /path/to/project/src/server.py"
          // ],
          "transport": "stdio",
          "workingDirectory": "/path/to/your/python-mcp-prompt-server" // Recommended
        }
        // ... other servers
      ]
    }
    ```
    *Replace paths with the actual absolute paths.*
    *Setting environment variables for commands launched by other applications (like Cursor) can be tricky and platform-dependent. Refer to your MCP client's documentation for the best way to set environment variables for server commands.*

**Raycast:**

1.  Configure a new MCP server in Raycast's settings.
2.  **Command:** `python` (or the absolute path to the Python executable in your virtual environment).
3.  **Argument(s):** Add the absolute path to `src/server.py`.
4.  **Working Directory (Optional but Recommended):** Set to the root of the `python-mcp-prompt-server` project.
5.  **Environment Variables (If supported by Raycast for commands):**
    *   `MCP_PROMPTS_DIR`: `/your/custom/prompts/path`
6.  **Transport:** Select `stdio`.

*(Similar configuration principles apply to Windsurf or other MCP-compatible clients.)*

## Available Tools

Besides the tools dynamically generated from your prompt files, the server provides these management tools:

*   **`get_prompt_names`**:
    *   **Description:** Lists the names of all currently available prompt-based tools.
    *   **Usage:** Call this tool with no arguments.
*   **`reload_prompts`**:
    *   **Description:** Rescans the configured prompts directory.
    *   **Usage:** Call this tool with no arguments.

## Contributing

Contributions are welcome!
1.  Fork and Clone.
2.  Create a new branch.
3.  Make changes.
4.  Test with `pytest`.
5.  Commit, Push, and open a Pull Request.

## License

[Specify License Here - e.g., This project is licensed under the MIT License.]
```
