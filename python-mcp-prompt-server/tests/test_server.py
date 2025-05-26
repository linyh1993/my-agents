import unittest
import os
import shutil
import asyncio
import yaml
from fastmcp import Client

# Make sure the server's global variables are initialized for testing context
# This might require careful structuring if the server auto-runs on import.
# For this test, we'll assume 'src.server' can be imported and then its
# functions like 'initial_load' and 'reload_all_prompts' can be called manually.
# We also need access to the 'mcp' instance from the server.
from src.server import mcp as mcp_server_instance, initial_load, reload_all_prompts, PROMPTS_DIR as SERVER_PROMPTS_DIR
from src.prompt_loader import load_prompts_from_directory # For verification

# Store original PROMPTS_DIR and override it for tests
ORIGINAL_PROMPTS_DIR = SERVER_PROMPTS_DIR
TEST_PROMPTS_DIR_NAME = "test_server_prompts_temp"

class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up a temporary directory for prompt files for all tests in this class.
        Override the server's PROMPTS_DIR.
        """
        cls.test_prompts_dir = os.path.abspath(TEST_PROMPTS_DIR_NAME)
        if os.path.exists(cls.test_prompts_dir):
            shutil.rmtree(cls.test_prompts_dir)
        os.makedirs(cls.test_prompts_dir, exist_ok=True)
        
        # Override server's PROMPTS_DIR.
        # This is a bit hacky; depends on how server.py is structured.
        # If server.py uses a global variable for PROMPTS_DIR that's directly referenced,
        # we can try to change it. This needs `src.server.PROMPTS_DIR = cls.test_prompts_dir`
        # but this change must happen *before* any function in server.py uses it.
        # For this setup, we assume server.PROMPTS_DIR can be patched or that
        # functions like load_prompts_from_directory take it as an argument (which it does not currently).
        # The current `src.server` defines PROMPTS_DIR globally. We will patch it.
        import src.server
        src.server.PROMPTS_DIR = cls.test_prompts_dir
        
        # print(f"Overriding PROMPTS_DIR to: {src.server.PROMPTS_DIR}")


    @classmethod
    def tearDownClass(cls):
        """
        Clean up the temporary directory after all tests.
        Restore original PROMPTS_DIR.
        """
        if os.path.exists(cls.test_prompts_dir):
            shutil.rmtree(cls.test_prompts_dir)
        import src.server
        src.server.PROMPTS_DIR = ORIGINAL_PROMPTS_DIR # Restore
        # print(f"Restored PROMPTS_DIR to: {src.server.PROMPTS_DIR}")


    def setUp(self):
        """
        Called before each test method.
        Ensures the test prompts directory is clean before each test
        and performs initial load into the test directory.
        """
        # Clear any files from previous test runs within this class
        for item in os.listdir(self.test_prompts_dir):
            item_path = os.path.join(self.test_prompts_dir, item)
            if os.path.isfile(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        
        # Reset MCP tools (important for test isolation)
        if hasattr(mcp_server_instance, 'tools') and isinstance(mcp_server_instance.tools, dict):
            mcp_server_instance.tools.clear()
        
        # Create some default prompts for general testing
        self._create_test_prompt_file("greeter.yaml", {
            "name": "Test Greeter",
            "description": "A simple greeter.",
            "arguments": [{"name": "name", "type": "string"}],
            "prompt_template": "Hello, {{name}}!"
        })
        self._create_test_prompt_file("calculator.yaml", {
            "name": "Test Calculator",
            "description": "A simple calculator.",
            "arguments": [
                {"name": "a", "type": "integer"},
                {"name": "b", "type": "integer"}
            ],
            "prompt_template": "Result: {{a}} + {{b}} = ? (not really calculated, just template)"
        })
        
        # Perform initial load using the overridden PROMPTS_DIR
        # initial_load() in server.py calls reload_all_prompts()
        # which uses the (now overridden) PROMPTS_DIR
        initial_load()


    def _create_test_prompt_file(self, filename, content):
        filepath = os.path.join(self.test_prompts_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(content, f)
        return filepath

    def test_01_initial_load_and_get_prompt_names(self):
        """Test that initial_load works and get_prompt_names returns initial prompts."""
        async def run_test():
            async with Client(mcp_server_instance) as client:
                prompt_names = await client.call_tool("get_prompt_names", {})
                # FastMCP typically returns a ToolResult object
                self.assertIsInstance(prompt_names.text, list) # Assuming .text holds the direct result
                self.assertIn("Test Greeter", prompt_names.text)
                self.assertIn("Test Calculator", prompt_names.text)
                self.assertNotIn("reload_prompts", prompt_names.text)
                self.assertNotIn("get_prompt_names", prompt_names.text)
        asyncio.run(run_test())

    def test_02_dynamic_tool_creation_and_execution(self):
        """Test if a dynamically created tool can be called and works as expected."""
        # Verify the 'Test Greeter' tool's function directly if possible (not easy with exec)
        # Instead, call it via the client, which is a better integration test.
        async def run_test():
            async with Client(mcp_server_instance) as client:
                result = await client.call_tool("Test Greeter", {"name": "Tester"})
                self.assertEqual(result.text, "Hello, Tester!")
        asyncio.run(run_test())

    def test_03_reload_prompts_add_new(self):
        """Test adding a new prompt and then reloading."""
        self._create_test_prompt_file("new_prompt.yaml", {
            "name": "New Prompt",
            "description": "A freshly added prompt.",
            "arguments": [],
            "prompt_template": "I am new!"
        })
        
        async def run_test():
            async with Client(mcp_server_instance) as client:
                # Verify it's not there yet
                prompt_names_before = await client.call_tool("get_prompt_names", {})
                self.assertNotIn("New Prompt", prompt_names_before.text)

                # Reload
                reload_status = await client.call_tool("reload_prompts", {})
                self.assertIn("Prompts reloaded", reload_status.text)
                
                # Verify it's there now
                prompt_names_after = await client.call_tool("get_prompt_names", {})
                self.assertIn("New Prompt", prompt_names_after.text)
                
                # Verify it works
                new_tool_result = await client.call_tool("New Prompt", {})
                self.assertEqual(new_tool_result.text, "I am new!")
        asyncio.run(run_test())

    def test_04_reload_prompts_modify_existing(self):
        """Test modifying an existing prompt (template) and then reloading."""
        # Modify 'Test Greeter'
        self._create_test_prompt_file("greeter.yaml", {
            "name": "Test Greeter", # Name must remain same to "modify"
            "description": "A simple greeter - modified.",
            "arguments": [{"name": "name", "type": "string"}],
            "prompt_template": "Hi there, {{name}}! How are you?" # Changed template
        })

        async def run_test():
            async with Client(mcp_server_instance) as client:
                # Call before reload
                result_before = await client.call_tool("Test Greeter", {"name": "OldTest"})
                self.assertEqual(result_before.text, "Hello, OldTest!") # Original template

                reload_status = await client.call_tool("reload_prompts", {})
                self.assertIn("Prompts reloaded", reload_status.text)

                # Call after reload
                result_after = await client.call_tool("Test Greeter", {"name": "NewTest"})
                self.assertEqual(result_after.text, "Hi there, NewTest! How are you?") # New template
        asyncio.run(run_test())


    def test_05_reload_prompts_delete_existing(self):
        """Test deleting a prompt file and then reloading."""
        prompt_to_delete = os.path.join(self.test_prompts_dir, "calculator.yaml")
        self.assertTrue(os.path.exists(prompt_to_delete))
        os.remove(prompt_to_delete)
        self.assertFalse(os.path.exists(prompt_to_delete))

        async def run_test():
            async with Client(mcp_server_instance) as client:
                # Verify it's there before reload
                prompt_names_before = await client.call_tool("get_prompt_names", {})
                self.assertIn("Test Calculator", prompt_names_before.text)

                reload_status = await client.call_tool("reload_prompts", {})
                self.assertIn("Prompts reloaded", reload_status.text)
                
                # Verify it's gone
                prompt_names_after = await client.call_tool("get_prompt_names", {})
                self.assertNotIn("Test Calculator", prompt_names_after.text)

                # Verify calling it fails (FastMCP client should raise an error for unknown tool)
                with self.assertRaises(Exception): # Or a more specific FastMCP client error
                    await client.call_tool("Test Calculator", {"a": 1, "b": 2})
        asyncio.run(run_test())

    def test_06_argument_types_and_defaults_in_dynamic_function(self):
        """Test a more complex prompt with types and defaults."""
        self._create_test_prompt_file("complex_prompt.yaml", {
            "name": "Complex Greeter",
            "description": "Greets with style.",
            "arguments": [
                {"name": "user_name", "type": "string", "description": "User's name."},
                {"name": "greeting", "type": "string", "required": False, "default": "Greetings"},
                {"name": "times", "type": "integer", "required": False, "default": 1},
                {"name": "show_details", "type": "boolean", "required": False, "default": False}
            ],
            "prompt_template": "{{greeting}}, {{user_name}}! (x{{times}}). Details: {{show_details}}"
        })
        # Reload to pick up this new prompt
        reload_all_prompts() 

        async def run_test():
            async with Client(mcp_server_instance) as client:
                # Test with all defaults
                result1 = await client.call_tool("Complex Greeter", {"user_name": "DefaultUser"})
                self.assertEqual(result1.text, "Greetings, DefaultUser! (x1). Details: False")

                # Test overriding defaults
                result2 = await client.call_tool("Complex Greeter", {
                    "user_name": "CustomUser",
                    "greeting": "Yo",
                    "times": 3,
                    "show_details": True
                })
                self.assertEqual(result2.text, "Yo, CustomUser! (x3). Details: True")
        asyncio.run(run_test())

    def test_07_sanitize_function_and_arg_names(self):
        """Test that names are sanitized correctly for exec."""
        # Create a prompt with names that need sanitization
        self._create_test_prompt_file("sanitize me.yaml", {
            "name": "Needs Sanitizing!",
            "description": "A prompt with characters that need to be sanitized.",
            "arguments": [
                {"name": "arg-1 with space", "type": "string"},
                {"name": "2ndArgStartsWithNumber", "type": "string", "required": False, "default": "num"},
            ],
            "prompt_template": "Sanitized: {{arg-1 with space}}, also {{2ndArgStartsWithNumber}}"
        })
        reload_all_prompts() # Reload to pick this up

        async def run_test():
            async with Client(mcp_server_instance) as client:
                # Check if the tool name (original) is registered
                prompt_names = await client.call_tool("get_prompt_names", {})
                self.assertIn("Needs Sanitizing!", prompt_names.text)

                # Call the tool
                result = await client.call_tool("Needs Sanitizing!", {
                    "arg-1 with space": "Value1",
                    "2ndArgStartsWithNumber": "Value2"
                })
                self.assertEqual(result.text, "Sanitized: Value1, also Value2")
                
                # Check another call where the optional arg is not provided
                result_default = await client.call_tool("Needs Sanitizing!", {
                    "arg-1 with space": "OnlyReq"
                })
                self.assertEqual(result_default.text, "Sanitized: OnlyReq, also num")


        asyncio.run(run_test())
        # The actual Python function name would be like 'dynamic_prompt_tool_Needs_Sanitizing'
        # and arg names 'arg_1_with_space', '_2ndArgStartsWithNumber'.
        # This test confirms it works through FastMCP, implying sanitization was successful.


if __name__ == '__main__':
    # Important: Ensure server.PROMPTS_DIR is patched *before* tests run.
    # This is handled by setUpClass for direct `python -m unittest` runs.
    # For pytest, ensure fixtures or conftest.py handle this if needed.
    unittest.main()
