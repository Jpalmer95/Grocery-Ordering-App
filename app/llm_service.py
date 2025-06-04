import requests # For making HTTP requests to Hugging Face API
import json # For parsing JSON responses
import google.generativeai as genai # For Google Gemini API
# Ensure google.auth.exceptions is available if you're catching it specifically.
# It's usually pulled in with google-auth, which is a dependency of google-generativeai.
import google.auth.exceptions

from . import db
from .models import UserSettings # UserSettings is used by init_llm_client, but not directly by the class anymore

class LLMServiceClient:
    def __init__(self, model_name="placeholder-model"): # API keys removed from constructor
        # API keys will now be passed per-call to generate/modify methods
        self.model_name = model_name
        print(f"LLMServiceClient initialized (key-agnostic at init).")

    def _call_huggingface_inference_api(self, model_id, hf_prompt, api_key):
        api_url = f"https://api-inference.huggingface.co/models/{model_id}"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "inputs": hf_prompt,
            "parameters": {"max_new_tokens": 1024, "return_full_text": False}, # Increased tokens
            "options": {"wait_for_model": True }
        }
        print(f"Calling HF API: {api_url} with prompt: '{hf_prompt[:100]}...'")
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=45) # Adjusted timeout
            response.raise_for_status()
            result = response.json()
            # print(f"HF API Response: {result}") # Can be very verbose
            if result and isinstance(result, list) and result[0].get('generated_text'):
                return result[0]['generated_text']
            elif result and isinstance(result, dict) and result.get('error'):
                return {'error': 'Hugging Face API Error', 'details': result.get('error')}
            else:
                return {'error': 'Hugging Face API Error', 'details': f"Unexpected response format: {str(result)[:200]}"}
        except requests.exceptions.Timeout:
            print(f"HF API Error: Request timed out.")
            return {'error': 'Hugging Face API Error', 'details': 'Request timed out.'}
        except requests.exceptions.HTTPError as e:
            error_text = e.response.text[:200] if hasattr(e.response, 'text') else 'No further details.'
            if e.response.status_code == 401:
                return {'error': 'Hugging Face API Error', 'details': 'Invalid API Key or unauthorized.'}
            return {'error': 'Hugging Face API Error', 'details': f"HTTP error: {e.response.status_code} - {error_text}"}
        except requests.exceptions.RequestException as e:
            print(f"HF API Error: Request failed - {e}")
            return {'error': 'Hugging Face API Error', 'details': f"Request failed: {str(e)}"}
        except json.JSONDecodeError as e:
            resp_text = response.text if 'response' in locals() and hasattr(response, 'text') else 'No response object'
            print(f"HF API Error: Failed to parse JSON response - {e}. Response text: {resp_text[:200]}")
            return {'error': 'Hugging Face API Error', 'details': f"Failed to parse JSON response: {str(e)}"}


    def _call_gemini_api(self, gemini_prompt, api_key):
        print(f"Calling Gemini API with prompt: '{gemini_prompt[:100]}...'")
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            # response = model.generate_content(gemini_prompt, request_options={'timeout': 45}) # Removed unsupported request_options
            response = model.generate_content(gemini_prompt)

            if response.parts:
                full_text = "".join(part.text for part in response.parts if hasattr(part, 'text'))
                if full_text:
                    # print(f"Gemini API Response Text: {full_text[:200]}...")
                    return full_text

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                print(f"Gemini API Error: Prompt blocked - {response.prompt_feedback.block_reason}")
                return {'error': 'Gemini API Content Filtered', 'details': f"Content generation blocked by API: {response.prompt_feedback.block_reason}"}

            print(f"Gemini API Error: No text in response and no block reason. Parts: {response.parts if hasattr(response, 'parts') else 'N/A'}")
            return {'error': 'Gemini API Error', 'details': 'No content generated or unexpected response structure.'}
        except google.auth.exceptions.RefreshError as e:
            print(f"Gemini API Authentication Error: {e}")
            return {'error': 'Gemini API Authentication Error', 'details': 'Failed to authenticate. Check API key and credentials.'}
        except Exception as e:
            print(f"Gemini API Error: {e}")
            if "API_KEY_INVALID" in str(e) or "API key not valid" in str(e):
                 return {'error': 'Gemini API Error', 'details': 'Invalid API Key provided.'}
            return {'error': 'Gemini API Error', 'details': str(e)}


    def _parse_recipe_text(self, generated_text, provider_name="AI"):
        if not generated_text or not isinstance(generated_text, str):
             return {'error': f'Invalid text received for parsing from {provider_name}',
                     'details': f'Received {type(generated_text).__name__} instead of string.'}
        try:
            lines = generated_text.strip().split('\n')
            recipe_data = {"name": f"{provider_name} Generated Recipe", "description": "", "ingredients": "", "instructions": ""}
            current_section = None
            ingredients_list = []
            instructions_list = []

            for line in lines:
                line_s = line.strip()
                if not line_s: continue # Skip empty lines

                line_l = line_s.lower()

                if line_l.startswith("recipe name:"):
                    recipe_data["name"] = line_s.split(":", 1)[1].strip()
                    current_section = None
                elif line_l.startswith("description:"):
                    recipe_data["description"] = line_s.split(":", 1)[1].strip()
                    current_section = "description"
                elif line_l.startswith("ingredients:"):
                    current_section = "ingredients"
                    # If the line itself is "Ingredients:", don't add it as an ingredient
                    if len(line_s.split(":", 1)) > 1 and line_s.split(":", 1)[1].strip():
                        ingredients_list.append(line_s.split(":", 1)[1].strip())
                elif line_l.startswith("instructions:"):
                    current_section = "instructions"
                    if len(line_s.split(":", 1)) > 1 and line_s.split(":", 1)[1].strip():
                        instructions_list.append(line_s.split(":", 1)[1].strip())
                elif current_section == "description":
                    if recipe_data["description"]: recipe_data["description"] += "\n" + line_s
                    else: recipe_data["description"] = line_s
                elif current_section == "ingredients":
                    ingredients_list.append(line_s)
                elif current_section == "instructions":
                    instructions_list.append(line_s)

            recipe_data["ingredients"] = "\n".join(ingredients_list)
            recipe_data["instructions"] = "\n".join(instructions_list)

            # Basic check if parsing yielded any content in crucial fields
            # If name is still the default or ingredients/instructions are empty, consider it a failure.
            is_default_name = recipe_data.get("name") == f"{provider_name} Generated Recipe" # Check against initial default
            if is_default_name and (not recipe_data["ingredients"] or not recipe_data["instructions"]):
                 print(f"Failed to parse structured recipe from {provider_name} (default name and missing fields). Name: '{recipe_data['name']}', Ing: '{recipe_data['ingredients'][:50]}...', Inst: '{recipe_data['instructions'][:50]}...'")
                 return {'error': f'Failed to understand {provider_name} response structure.',
                         'details': f"Raw output: {generated_text[:500]}...",
                         'name': f"{provider_name} Recipe (Parsing Failed)", # Standardize name on parsing failure
                         'description': recipe_data.get("description") or generated_text,
                         'ingredients': recipe_data.get("ingredients") or "", 'instructions': recipe_data.get("instructions") or ""}
            elif not recipe_data["ingredients"] or not recipe_data["instructions"]: # Name might be parsed, but other fields missing
                 print(f"Failed to parse structured recipe from {provider_name} (missing fields). Name: '{recipe_data['name']}', Ing: '{recipe_data['ingredients'][:50]}...', Inst: '{recipe_data['instructions'][:50]}...'")
                 return {'error': f'Failed to understand {provider_name} response structure.',
                         'details': f"Raw output: {generated_text[:500]}...",
                         'name': f"{provider_name} Recipe (Parsing Failed)" if is_default_name else recipe_data.get("name"), # Use parsed name if not default, else failure name
                         'description': recipe_data.get("description") or generated_text,
                         'ingredients': recipe_data.get("ingredients") or "", 'instructions': recipe_data.get("instructions") or ""}
            return recipe_data
        except Exception as e:
            print(f"Error parsing generated recipe text from {provider_name}: {e}")
            return {'error': f'Error parsing {provider_name} response', 'details': str(e),
                    'name': f"{provider_name} Recipe (Parsing Error)",
                    'description': generated_text, 'ingredients': '', 'instructions': ''} # Use raw text for desc


    def generate_recipe(self, user_prompt, provider="placeholder", api_keys=None):
        if api_keys is None: api_keys = {}
        generated_text_or_error = None
        provider_name_for_title = provider.replace("_", " ").title() if provider != "placeholder" else "AI"


        if provider == "hugging_face" and api_keys.get('hugging_face'):
            hf_prompt = (
                f"Generate a detailed recipe based on the following request: '{user_prompt}'.\n\n"
                "Please provide the output in the following structure:\n"
                "Recipe Name: [Name of the recipe]\n"
                "Description: [A short description of the dish]\n"
                "Ingredients:\n[Ingredient 1]\n[Ingredient 2]\n[...]\n"
                "Instructions:\n1. [Step 1]\n2. [Step 2]\n[...]"
            )
            generated_text_or_error = self._call_huggingface_inference_api("mistralai/Mistral-7B-Instruct-v0.1", hf_prompt, api_keys['hugging_face'])

        elif provider == "gemini" and api_keys.get('gemini'):
            gemini_prompt = (
                f"Generate a creative and detailed recipe for: '{user_prompt}'.\n\n"
                "Output structure should be:\n"
                "Recipe Name: [Name of the recipe]\n"
                "Description: [A short description of the dish]\n"
                "Ingredients:\n- [Ingredient 1]\n- [Ingredient 2]\n- [...]\n"
                "Instructions:\n1. [Step 1]\n2. [Step 2]\n[...]"
            )
            generated_text_or_error = self._call_gemini_api(gemini_prompt, api_keys['gemini'])

        if generated_text_or_error: # This means an API call was attempted
            if isinstance(generated_text_or_error, dict) and 'error' in generated_text_or_error:
                # Add provider name to error context if not already there
                generated_text_or_error['provider_name'] = provider_name_for_title
                return generated_text_or_error

            parsed_recipe = self._parse_recipe_text(generated_text_or_error, provider_name_for_title)
            if isinstance(parsed_recipe, dict) and 'error' in parsed_recipe:
                 # Add provider name to error context if not already there
                parsed_recipe['provider_name'] = provider_name_for_title
                return parsed_recipe
            parsed_recipe["is_ai_generated"] = True
            return parsed_recipe

        # Fallback to placeholder if no provider was matched or if API calls returned None without specific error dict
        if provider != "placeholder":
             return {'error': f'{provider_name_for_title} API Error', 'details': 'Failed to get a valid response or key not configured.', 'name': f"{provider_name_for_title} Recipe (API Error)"}

        print(f"LLMService: Using placeholder for generate_recipe. Prompt: '{user_prompt}'")
        if "pasta" in user_prompt.lower():
            recipe_name = "AI Generated Pasta Dish (Placeholder)"
            description = "A delightful pasta dish, imagined by AI."
            ingredients = "Pasta\nTomato Sauce\nCheese\nHerbs (AI's choice)"
            instructions = "1. Cook pasta.\n2. Heat sauce.\n3. Combine pasta, sauce, and cheese.\n4. Sprinkle with AI-chosen herbs.\n5. Serve hot and enjoy your AI creation!"
        elif "chicken" in user_prompt.lower():
            recipe_name = "AI Generated Chicken Delight (Placeholder)"
            description = "A surprising chicken recipe from the mind of an AI."
            ingredients = "Chicken Breast\nAI's Secret Spice Mix\nVegetables (AI's selection)"
            instructions = "1. Marinate chicken with AI's secret spices.\n2. Cook chicken until golden.\n3. Serve with AI-selected vegetables.\n4. Marvel at the AI's culinary prowess."
        else:
            recipe_name = "Mysterious AI Recipe (Placeholder)"
            description = "An enigmatic recipe generated by our AI chef."
            ingredients = "1 cup of AI Whimsy\n2 tbsp of Algorithmic Flavor\nA pinch of Neural Spice"
            instructions = "1. Mix AI Whimsy with Algorithmic Flavor.\n2. Gently fold in Neural Spice.\n3. Bake at 350°F until the AI deems it ready.\n4. Contemplate the nature of AI-generated cuisine."
        return {
            "name": recipe_name, "description": description,
            "ingredients": ingredients, "instructions": instructions,
            "is_ai_generated": True
        }

    def modify_recipe(self, original_recipe_data, user_prompt, provider="placeholder", api_keys=None):
        if api_keys is None: api_keys = {}
        modified_text_or_error = None
        provider_name_for_title = provider.replace("_", " ").title() if provider != "placeholder" else "AI"

        if provider == "hugging_face" and api_keys.get('hugging_face'):
            hf_prompt = (
                f"Original Recipe:\nName: {original_recipe_data.get('name')}\nDescription: {original_recipe_data.get('description')}\nIngredients:\n{original_recipe_data.get('ingredients')}\nInstructions:\n{original_recipe_data.get('instructions')}\n\n"
                f"User request: Modify this recipe to '{user_prompt}'.\n\n"
                "Please provide the full modified recipe in the following structure:\nRecipe Name: [New Name]\nDescription: [New Description]\nIngredients:\n[Ingredient 1]\n[...]\nInstructions:\n1. [Step 1]\n[...]"
            )
            modified_text_or_error = self._call_huggingface_inference_api("mistralai/Mistral-7B-Instruct-v0.1", hf_prompt, api_keys['hugging_face'])

        elif provider == "gemini" and api_keys.get('gemini'):
            gemini_prompt = (
                f"Original Recipe:\nName: {original_recipe_data.get('name')}\nDescription: {original_recipe_data.get('description')}\nIngredients:\n{original_recipe_data.get('ingredients')}\nInstructions:\n{original_recipe_data.get('instructions')}\n\n"
                f"User request: Modify this recipe to '{user_prompt}'.\n\n"
                "Output the full modified recipe with this structure:\nRecipe Name: [New Name]\nDescription: [New Description]\nIngredients:\n- [Ingredient 1]\n- [...]\nInstructions:\n1. [Step 1]\n[...]"
            )
            modified_text_or_error = self._call_gemini_api(gemini_prompt, api_keys['gemini'])

        if modified_text_or_error: # API call was attempted
            if isinstance(modified_text_or_error, dict) and 'error' in modified_text_or_error:
                modified_text_or_error['provider_name'] = provider_name_for_title
                return modified_text_or_error

            parsed_recipe = self._parse_recipe_text(modified_text_or_error, provider_name_for_title)
            if isinstance(parsed_recipe, dict) and 'error' in parsed_recipe:
                parsed_recipe['provider_name'] = provider_name_for_title
                return parsed_recipe
            parsed_recipe["is_ai_modified"] = True
            return parsed_recipe

        if provider != "placeholder": # API call was attempted but failed earlier
             return {'error': f'{provider_name_for_title} API Error', 'details': 'Failed to get a valid response or key not configured for modification.', 'name': f"{provider_name_for_title} Modified (API Error)"}

        # Fallback to placeholder
        print(f"LLMService: Using placeholder for modify_recipe. Prompt: '{user_prompt}' for recipe '{original_recipe_data.get('name', 'Unknown')}'")
        modified_data_ph = original_recipe_data.copy()
        if "vegetarian" in user_prompt.lower():
            modified_data_ph["name"] = original_recipe_data.get("name", "") + " (Vegetarian AI Remix - Placeholder)"
            modified_data_ph["description"] = original_recipe_data.get("description", "") + " Now with a vegetarian twist from our AI!"
            modified_data_ph["ingredients"] = original_recipe_data.get("ingredients", "").replace("Chicken", "Tofu").replace("Beef", "Mushrooms") + "\n1 dash of AI Vegetarian Magic"
            modified_data_ph["instructions"] = original_recipe_data.get("instructions", "") + "\nAI Chef's Note: Ensure all animal products are lovingly replaced with plant-based alternatives."
        elif "spicy" in user_prompt.lower():
            modified_data_ph["name"] = original_recipe_data.get("name", "") + " (Spicy AI Edition - Placeholder)"
            modified_data_ph["description"] = original_recipe_data.get("description", "") + " This version has an extra kick, thanks to AI!"
            modified_data_ph["ingredients"] = original_recipe_data.get("ingredients", "") + "\n1 tsp AI Fire Powder\nRed Chili Flakes (to taste, as per AI)"
            modified_data_ph["instructions"] = original_recipe_data.get("instructions", "") + "\nAI Warning: May be too spicy for some humans. Handle AI Fire Powder with care."
        else:
            modified_data_ph["name"] = original_recipe_data.get("name", "") + " (AI Re-imagined - Placeholder)"
            modified_data_ph["description"] = original_recipe_data.get("description", "") + " AI has thoughtfully considered your request and made some... changes."
            modified_data_ph["instructions"] = "AI has decided to rewrite the instructions: \n1. Contemplate the original recipe. \n2. Imagine the prompt. \n3. The new recipe is now self-evident (according to the AI)."
            modified_data_ph["ingredients"] = original_recipe_data.get("ingredients", "") + "\n1 tbsp Unpredictable AI Essence"
        modified_data_ph["is_ai_modified"] = True
        return modified_data_ph


llm_client = LLMServiceClient()

def init_llm_client(app):
    global llm_client
    # Keys are no longer pre-loaded into the global client at app startup.
    # They will be fetched from current_user.settings in routes and passed per-call.
    llm_client = LLMServiceClient()
    print(f"Global LLMServiceClient instance created by init_llm_client (key-agnostic).")


def get_llm_client():
    return llm_client
