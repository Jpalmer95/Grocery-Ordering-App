import unittest
from unittest.mock import patch, Mock
from app.llm_service import LLMServiceClient # Import the class to test
import app.llm_service as llm_service_module # To patch the global client if needed by routes
import requests # To mock requests.exceptions if needed
import google.auth.exceptions # To mock google auth exceptions

# Example structured output for mocking
mock_hf_good_output = "Recipe Name: HF Test Pasta\nDescription: A delicious pasta from HF.\nIngredients:\nPasta\nSauce\nCheese\nInstructions:\n1. Cook pasta.\n2. Add sauce.\n3. Add cheese."
mock_gemini_good_output = "Recipe Name: Gemini Test Salad\nDescription: A fresh salad from Gemini.\nIngredients:\n- Lettuce\n- Tomato\n- Cucumber\nInstructions:\n1. Chop veggies.\n2. Mix.\n3. Serve."

class TestLLMService(unittest.TestCase):
    def setUp(self):
        # We can instantiate the client directly for more focused unit tests
        self.hf_api_key = "dummy_hf_key" # Still useful for passing to methods
        self.gemini_api_key = "dummy_gemini_key" # Still useful for passing to methods
        self.client = LLMServiceClient() # Constructor is now key-agnostic

        # Also, get the global client from the module if we want to test its state
        # after app initialization (though app context for DB might be tricky here)
        # For now, focusing on direct LLMServiceClient tests.

    # --- Tests for generate_recipe ---

    @patch('app.llm_service.requests.post')
    def test_generate_recipe_huggingface_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'generated_text': mock_hf_good_output}]
        mock_post.return_value = mock_response

        user_prompt = "a pasta dish"
        api_keys = {'hugging_face': self.hf_api_key}
        result = self.client.generate_recipe(user_prompt, provider="hugging_face", api_keys=api_keys)

        mock_post.assert_called_once()
        # Basic check for call args (more detailed checks can be added for headers/payload)
        self.assertTrue("api-inference.huggingface.co" in mock_post.call_args[0][0])
        self.assertEqual(result['name'], "HF Test Pasta")
        self.assertIn("delicious pasta from HF", result['description'])
        self.assertIn("Pasta", result['ingredients'])
        self.assertIn("Cook pasta", result['instructions'])
        self.assertTrue(result.get('is_ai_generated'))

    @patch('app.llm_service.requests.post')
    def test_generate_recipe_huggingface_api_error(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 401 # Unauthorized
        mock_response.json.return_value = {"error": "Unauthorized"}
        mock_response.text = 'Mocked error: Unauthorized' # Add this
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        user_prompt = "a test dish"
        api_keys = {'hugging_face': self.hf_api_key}
        result = self.client.generate_recipe(user_prompt, provider="hugging_face", api_keys=api_keys)

        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Hugging Face API Error')
        self.assertIn('Invalid API Key or unauthorized', result['details'])

    @patch('app.llm_service.requests.post')
    def test_generate_recipe_huggingface_timeout(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout

        user_prompt = "a test dish"
        api_keys = {'hugging_face': self.hf_api_key}
        result = self.client.generate_recipe(user_prompt, provider="hugging_face", api_keys=api_keys)

        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Hugging Face API Error')
        self.assertEqual(result['details'], 'Request timed out.')

    @patch('app.llm_service.genai.GenerativeModel')
    @patch('app.llm_service.genai.configure')
    def test_generate_recipe_gemini_success(self, mock_configure, mock_generative_model):
        mock_model_instance = Mock()
        mock_gemini_response = Mock()
        mock_gemini_response.text = mock_gemini_good_output
        mock_gemini_response.parts = [Mock(text=mock_gemini_good_output)]
        mock_gemini_response.prompt_feedback = None # No blocking
        mock_model_instance.generate_content.return_value = mock_gemini_response
        mock_generative_model.return_value = mock_model_instance

        user_prompt = "a salad"
        api_keys = {'gemini': self.gemini_api_key}
        result = self.client.generate_recipe(user_prompt, provider="gemini", api_keys=api_keys)

        mock_configure.assert_called_once_with(api_key=self.gemini_api_key)
        mock_model_instance.generate_content.assert_called_once()
        self.assertEqual(result['name'], "Gemini Test Salad")
        self.assertIn("fresh salad from Gemini", result['description'])
        self.assertIn("Lettuce", result['ingredients'])
        self.assertIn("Chop veggies", result['instructions'])
        self.assertTrue(result.get('is_ai_generated'))

    @patch('app.llm_service.genai.GenerativeModel')
    @patch('app.llm_service.genai.configure')
    def test_generate_recipe_gemini_api_key_error(self, mock_configure, mock_generative_model):
        # Simulate an API key error during configure or model instantiation
        mock_configure.side_effect = google.auth.exceptions.RefreshError("Invalid API Key")

        user_prompt = "a test dish"
        api_keys = {'gemini': self.gemini_api_key}
        result = self.client.generate_recipe(user_prompt, provider="gemini", api_keys=api_keys)

        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Gemini API Authentication Error')
        self.assertIn('Failed to authenticate', result['details'])

    @patch('app.llm_service.genai.GenerativeModel')
    @patch('app.llm_service.genai.configure')
    def test_generate_recipe_gemini_content_blocked(self, mock_configure, mock_generative_model):
        mock_model_instance = Mock()
        mock_gemini_response = Mock()
        mock_gemini_response.text = None # No text if blocked
        mock_gemini_response.parts = []
        mock_gemini_response.prompt_feedback = Mock(block_reason="SAFETY")
        mock_model_instance.generate_content.return_value = mock_gemini_response
        mock_generative_model.return_value = mock_model_instance

        user_prompt = "a harmful dish"
        api_keys = {'gemini': self.gemini_api_key}
        result = self.client.generate_recipe(user_prompt, provider="gemini", api_keys=api_keys)

        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Gemini API Content Filtered')
        self.assertIn("Content generation blocked by API: SAFETY", result['details'])


    def test_generate_recipe_placeholder(self):
        user_prompt = "a chicken dish"
        result = self.client.generate_recipe(user_prompt, provider="placeholder", api_keys={})
        self.assertEqual(result['name'], "AI Generated Chicken Delight (Placeholder)")
        self.assertTrue(result.get('is_ai_generated'))

    def test_generate_recipe_missing_key_fallback_to_placeholder(self):
        user_prompt = "a pasta dish"
        # No key for gemini, should return an error
        result = self.client.generate_recipe(user_prompt, provider="gemini", api_keys={'hugging_face': 'some_key'})
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Gemini API Error')
        self.assertIn('key not configured', result['details'].lower()) # Check for key missing detail
        self.assertNotIn('is_ai_generated', result) # Should not have this flag if it's an error dict


    # --- Tests for modify_recipe (similar structure) ---

    @patch('app.llm_service.requests.post')
    def test_modify_recipe_huggingface_success(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        # Assume the LLM returns a modified version based on the prompt
        modified_text = "Recipe Name: HF Modified Soup\nDescription: Soup, now less soupy.\nIngredients:\nWater (less)\nSalt\nInstructions:\n1. Boil less water.\n2. Add salt."
        mock_response.json.return_value = [{'generated_text': modified_text}]
        mock_post.return_value = mock_response

        original_recipe = {"name": "Original Soup", "ingredients": "Water\nSalt", "instructions": "Boil water. Add salt.", "description": "Just soup."}
        user_prompt = "make it less soupy"
        api_keys = {'hugging_face': self.hf_api_key}
        result = self.client.modify_recipe(original_recipe, user_prompt, provider="hugging_face", api_keys=api_keys)

        mock_post.assert_called_once()
        self.assertEqual(result['name'], "HF Modified Soup")
        self.assertIn("less soupy", result['description'])
        self.assertTrue(result.get('is_ai_modified'))

    @patch('app.llm_service.genai.GenerativeModel')
    @patch('app.llm_service.genai.configure')
    def test_modify_recipe_gemini_success(self, mock_configure, mock_generative_model):
        mock_model_instance = Mock()
        modified_text = "Recipe Name: Gemini Modified Cake\nDescription: Cake, now gluten-free.\nIngredients:\n- GF Flour\n- Sugar\nInstructions:\n1. Mix GF flour and sugar.\n2. Bake."
        mock_gemini_response = Mock(text=modified_text, parts=[Mock(text=modified_text)], prompt_feedback=None)
        mock_model_instance.generate_content.return_value = mock_gemini_response
        mock_generative_model.return_value = mock_model_instance

        original_recipe = {"name": "Original Cake", "ingredients": "Flour\nSugar", "instructions": "Mix. Bake.", "description": "A simple cake."}
        user_prompt = "make it gluten-free"
        api_keys = {'gemini': self.gemini_api_key}
        result = self.client.modify_recipe(original_recipe, user_prompt, provider="gemini", api_keys=api_keys)

        mock_configure.assert_called_once_with(api_key=self.gemini_api_key)
        self.assertEqual(result['name'], "Gemini Modified Cake")
        self.assertIn("gluten-free", result['description'])
        self.assertTrue(result.get('is_ai_modified'))

    def test_modify_recipe_placeholder(self):
        original_recipe = {"name": "Chicken Stir-fry", "ingredients": "Chicken\nSoy Sauce\nVegetables", "instructions": "Stir-fry everything.", "description": "Quick stir-fry."}
        user_prompt = "make it vegetarian"
        result = self.client.modify_recipe(original_recipe, user_prompt, provider="placeholder", api_keys={})

        self.assertEqual(result['name'], "Chicken Stir-fry (Vegetarian AI Remix - Placeholder)") # Corrected expected name
        self.assertIn("Tofu", result['ingredients'])
        self.assertTrue(result.get('is_ai_modified'))

    # --- Tests for _parse_recipe_text ---
    def test_parse_recipe_text_success(self):
        text = "Recipe Name: My Test Recipe\nDescription: Test desc.\nIngredients:\nIng 1\nIng 2\nInstructions:\nStep 1\nStep 2"
        result = self.client._parse_recipe_text(text, "TestProvider")
        self.assertEqual(result['name'], "My Test Recipe")
        self.assertEqual(result['description'], "Test desc.")
        self.assertEqual(result['ingredients'], "Ing 1\nIng 2")
        self.assertEqual(result['instructions'], "Step 1\nStep 2")

    def test_parse_recipe_text_malformed(self):
        text = "This is not a recipe."
        result = self.client._parse_recipe_text(text, "TestProvider")
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Failed to understand TestProvider response structure.')
        self.assertIn('Raw output: This is not a recipe.', result['details'])
        self.assertEqual(result['name'], "TestProvider Recipe (Parsing Failed)") # Corrected expected name

    def test_parse_recipe_text_empty_input(self):
        result = self.client._parse_recipe_text("", "TestProvider")
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Invalid text received for parsing from TestProvider')

    def test_parse_recipe_text_none_input(self):
        result = self.client._parse_recipe_text(None, "TestProvider")
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Invalid text received for parsing from TestProvider')


if __name__ == '__main__':
    unittest.main()
