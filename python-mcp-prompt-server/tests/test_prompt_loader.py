import unittest
import os
import shutil
import yaml
import json
from src.prompt_loader import load_prompts_from_directory, TYPE_MAPPING

class TestPromptLoader(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_prompts_temp"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _create_prompt_file(self, filename, content, is_yaml=True):
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            if is_yaml:
                yaml.dump(content, f)
            else:
                json.dump(content, f)
        return filepath

    def test_load_valid_yaml_prompt(self):
        content = {
            "name": "Test YAML Prompt",
            "description": "A test prompt in YAML.",
            "arguments": [{"name": "arg1", "type": "string"}],
            "prompt_template": "Hello {{arg1}}"
        }
        self._create_prompt_file("test_yaml.yaml", content)
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["name"], "Test YAML Prompt")
        self.assertEqual(prompts[0]["arguments"][0]["type"], str)

    def test_load_valid_json_prompt(self):
        content = {
            "name": "Test JSON Prompt",
            "description": "A test prompt in JSON.",
            "arguments": [{"name": "arg1", "type": "integer"}],
            "prompt_template": "Value: {{arg1}}"
        }
        self._create_prompt_file("test_json.json", content, is_yaml=False)
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["name"], "Test JSON Prompt")
        self.assertEqual(prompts[0]["arguments"][0]["type"], int)

    def test_missing_required_fields(self):
        # Missing 'description'
        content_missing_desc = {
            "name": "Incomplete Prompt",
            "arguments": [],
            "prompt_template": "Template"
        }
        self._create_prompt_file("missing_desc.yaml", content_missing_desc)
        
        # Missing 'name'
        content_missing_name = {
            "description": "Desc only",
            "arguments": [],
            "prompt_template": "Template"
        }
        self._create_prompt_file("missing_name.yaml", content_missing_name)

        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 0, "Prompts with missing fields should be skipped.")

    def test_argument_parsing(self):
        content = {
            "name": "Arg Parse Test",
            "description": "Testing argument parsing.",
            "arguments": [
                {"name": "name_arg", "description": "A name.", "type": "string"},
                {"name": "age_arg", "type": "integer", "required": True},
                {"name": "active_arg", "type": "boolean", "required": False, "default": True},
                {"name": "score_arg", "type": "number", "required": False, "default": 0.5},
                {"name": "default_type_arg"}, # Should default to type str, required True
                {"name": "str_default_bool", "type": "boolean", "required": False, "default": "false"},
                {"name": "str_default_int", "type": "integer", "required": False, "default": "123"},
                {"name": "str_default_float", "type": "number", "required": False, "default": "1.23"},
                {"name": "invalid_default_type", "type": "integer", "required": False, "default": "not-an-int"},
            ],
            "prompt_template": "Template: {{name_arg}}, {{age_arg}}, {{active_arg}}, {{score_arg}}"
        }
        self._create_prompt_file("arg_parse.yaml", content)
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 1)
        
        args = {arg['name']: arg for arg in prompts[0]['arguments']}

        self.assertEqual(args["name_arg"]["type"], str)
        self.assertEqual(args["name_arg"]["description"], "A name.")
        self.assertTrue(args["name_arg"]["required"]) # Default required is True

        self.assertEqual(args["age_arg"]["type"], int)
        self.assertTrue(args["age_arg"]["required"])

        self.assertEqual(args["active_arg"]["type"], bool)
        self.assertFalse(args["active_arg"]["required"])
        self.assertEqual(args["active_arg"]["default"], True)
        
        self.assertEqual(args["score_arg"]["type"], float) # 'number' maps to float
        self.assertFalse(args["score_arg"]["required"])
        self.assertEqual(args["score_arg"]["default"], 0.5)

        self.assertEqual(args["default_type_arg"]["type"], str) # Default type
        self.assertTrue(args["default_type_arg"]["required"]) # Default required
        self.assertIsNone(args["default_type_arg"]["default"])

        self.assertEqual(args["str_default_bool"]["type"], bool)
        self.assertEqual(args["str_default_bool"]["default"], False)

        self.assertEqual(args["str_default_int"]["type"], int)
        self.assertEqual(args["str_default_int"]["default"], 123)
        
        self.assertEqual(args["str_default_float"]["type"], float)
        self.assertEqual(args["str_default_float"]["default"], 1.23)

        self.assertEqual(args["invalid_default_type"]["type"], int)
        self.assertIsNone(args["invalid_default_type"]["default"], "Default should be None due to type mismatch")


    def test_empty_directory(self):
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 0)

    def test_directory_with_invalid_files(self):
        self._create_prompt_file("not_a_prompt.txt", {"text": "hello"}, is_yaml=False) # create as json for simplicity
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 0)
        
    def test_empty_prompt_file(self):
        filepath = os.path.join(self.test_dir, "empty.yaml")
        with open(filepath, 'w') as f:
            f.write("") # Empty file
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 0, "Empty prompt files should be skipped or handled gracefully.")

    def test_malformed_yaml_prompt_file(self):
        filepath = os.path.join(self.test_dir, "malformed.yaml")
        with open(filepath, 'w') as f:
            f.write("name: Test\ndescription: Test\n  bad_indent: Template") # Malformed YAML
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 0, "Malformed YAML files should be skipped.")

    def test_malformed_json_prompt_file(self):
        filepath = os.path.join(self.test_dir, "malformed.json")
        with open(filepath, 'w') as f:
            f.write('{"name": "Test", "description": "Test", "prompt_template": "Template"') # Missing closing brace
        prompts = load_prompts_from_directory(self.test_dir)
        self.assertEqual(len(prompts), 0, "Malformed JSON files should be skipped.")

    def test_argument_type_mapping(self):
        self.assertEqual(TYPE_MAPPING["string"], str)
        self.assertEqual(TYPE_MAPPING["integer"], int)
        self.assertEqual(TYPE_MAPPING["boolean"], bool)
        self.assertEqual(TYPE_MAPPING["number"], float)
        # Test default for unknown type in loader
        self.assertEqual(TYPE_MAPPING.get("unknown", str), str)

if __name__ == '__main__':
    unittest.main()
