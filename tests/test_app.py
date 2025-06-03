import unittest
from flask import url_for
from urllib.parse import urlparse, parse_qs # Ensure this is at the top and correctly placed
from app import app, db
from app.models import Recipe

class AppTestCase(unittest.TestCase):

    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory DB for tests
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for simpler form testing
        app.config['SERVER_NAME'] = 'localhost.test' # Added for url_for outside request context
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_home_page(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome to My Recipe App!', response.data)
        self.assertIn(b'This is the home page.', response.data)

    def test_recipes_page(self):
        response = self.app.get('/recipes')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Recipes', response.data)
        self.assertIn(b'Add New Recipe', response.data)
        # Initially, no recipes
        self.assertIn(b'No recipes found.', response.data)

    def test_add_recipe_page_get(self):
        response = self.app.get('/recipe/add')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Add a New Recipe', response.data)
        self.assertIn(b'Recipe Name:', response.data)

    def test_add_and_view_recipe(self):
        # Add a recipe
        response_post = self.app.post('/recipe/add', data=dict(
            name='Test Soup',
            description='A tasty test soup',
            ingredients='Water\nCarrots\nSalt',
            instructions='Boil water\nAdd carrots\nAdd salt'
        ), follow_redirects=True)
        self.assertEqual(response_post.status_code, 200)
        self.assertIn(b'Test Soup', response_post.data)
        self.assertIn(b'A tasty test soup', response_post.data)
        self.assertNotIn(b'No recipes found.', response_post.data)

        # Verify it's in the database (optional, but good practice)
        recipe = Recipe.query.filter_by(name='Test Soup').first()
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.description, 'A tasty test soup')

        # Check if the recipe list page now shows the recipe
        response_get_recipes = self.app.get('/recipes')
        self.assertEqual(response_get_recipes.status_code, 200)
        self.assertIn(b'Test Soup', response_get_recipes.data)
        self.assertIn(b'A tasty test soup', response_get_recipes.data)

    def _add_test_recipe(self, name="Default Recipe", description="Default Desc", ingredients="Default Ing", instructions="Default Inst"):
        recipe = Recipe(name=name, description=description, ingredients=ingredients, instructions=instructions)
        db.session.add(recipe)
        db.session.commit()
        return recipe

    def test_edit_recipe_get(self):
        recipe = self._add_test_recipe(name="Original Name")
        response = self.app.get(f'/recipe/{recipe.id}/edit')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Edit Recipe: Original Name', response.data)
        self.assertIn(b'Original Name', response.data) # Check if form is pre-filled

    def test_edit_recipe_post(self):
        recipe = self._add_test_recipe(name="Old Name", description="Old Desc")
        response = self.app.post(f'/recipe/{recipe.id}/edit', data=dict(
            name='New Name',
            description='New Desc',
            ingredients=recipe.ingredients, # Keep old ingredients
            instructions=recipe.instructions # Keep old instructions
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'New Name', response.data)
        self.assertIn(b'New Desc', response.data)
        self.assertNotIn(b'Old Name', response.data)

        # Verify in DB
        updated_recipe = db.session.get(Recipe, recipe.id)
        self.assertEqual(updated_recipe.name, 'New Name')
        self.assertEqual(updated_recipe.description, 'New Desc')

    def test_delete_recipe(self):
        recipe = self._add_test_recipe(name="To Be Deleted")
        recipe_id = recipe.id

        # Ensure it's on the page first
        response_get = self.app.get('/recipes')
        self.assertIn(b'To Be Deleted', response_get.data)

        response_post = self.app.post(f'/recipe/{recipe_id}/delete', follow_redirects=True)
        self.assertEqual(response_post.status_code, 200)
        self.assertNotIn(b'To Be Deleted', response_post.data)
        self.assertIn(b'No recipes found.', response_post.data) # Assuming it's the only recipe

        # Verify in DB
        deleted_recipe = db.session.get(Recipe, recipe_id)
        self.assertIsNone(deleted_recipe)

    def test_grocery_list_page(self):
        response = self.app.get('/grocery-list')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Grocery List', response.data)
        self.assertIn(b'Select recipes from the', response.data) # Check for default empty message

    def test_generate_grocery_list_no_selection(self):
        response = self.app.post('/generate-grocery-list', data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        # Should redirect back to recipes page or show a message on grocery list page
        # Current implementation redirects to recipes if no IDs
        self.assertIn(b'Recipes', response.data) # Check if it redirected to recipes page

    def test_generate_grocery_list_with_selection(self):
        # Add some recipes
        recipe1 = self._add_test_recipe(name="Pasta Bake", ingredients="Pasta\nTomato Sauce\nCheese")
        recipe2 = self._add_test_recipe(name="Salad", ingredients="Lettuce\nTomato\nCucumber\nCheese") # Cheese is common
        recipe3 = self._add_test_recipe(name="Bread", ingredients="Flour\nWater\nSalt\nYeast") # No common ingredients with others

        # Select Pasta Bake and Salad
        selected_ids = [str(recipe1.id), str(recipe2.id)]
        response = self.app.post('/generate-grocery-list', data={'recipe_ids': selected_ids})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generated Grocery List', response.data)

        # Check for aggregated ingredients (order might vary due to set conversion, so check presence)
        # With current implementation (sorted list of unique capitalized ingredients, with counts):
        self.assertIn(b'Cheese (x2)', response.data)
        self.assertIn(b'Cucumber', response.data)
        self.assertIn(b'Lettuce', response.data)
        self.assertIn(b'Pasta', response.data)
        self.assertIn(b'Tomato', response.data)
        self.assertIn(b'Tomato sauce', response.data) # Check for case sensitivity and spacing

        self.assertNotIn(b'Flour', response.data) # From recipe3, which was not selected

    def test_generate_grocery_list_single_recipe(self):
        recipe = self._add_test_recipe(name="Simple Soup", ingredients="Broth\nCarrots\nCelery")
        selected_ids = [str(recipe.id)]
        response = self.app.post('/generate-grocery-list', data={'recipe_ids': selected_ids})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generated Grocery List', response.data)
        self.assertIn(b'Broth', response.data)
        self.assertIn(b'Carrots', response.data)
        self.assertIn(b'Celery', response.data)
        self.assertNotIn(b'(x', response.data) # No counts for single items

    def test_order_with_instacart_flow(self):
        # First, generate a grocery list to have some ingredients
        recipe = self._add_test_recipe(name="Test Dish", ingredients="Ingredient A (x2)\nIngredient B")
        # The generate_grocery_list route expects raw ingredients and then formats them.
        # For this test, we'll manually create a list of formatted ingredients
        # as they would be submitted from the grocery_list.html form.
        formatted_ingredients_from_list_page = ["Ingredient A (x2)", "Ingredient B"]

        response = self.app.post('/order-instacart', data={'ingredients': formatted_ingredients_from_list_page})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Order with InstaCart (Simulated)', response.data)

        self.assertIn(b'Ingredient A (x2)', response.data)
        self.assertIn(b'Find on InstaCart', response.data)
        self.assertIn(b'Ingredient B', response.data)

    def test_order_with_instacart_no_ingredients(self):
        response = self.app.post('/order-instacart', data={'ingredients': []})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Order with InstaCart (Simulated)', response.data)
        self.assertIn(b'No ingredients were sent to order.', response.data)

    def test_generate_recipe_llm_get(self):
        response = self.app.get('/generate-recipe-llm')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generate a New Recipe with AI', response.data)
        self.assertIn(b'What kind of recipe would you like?', response.data)

    def test_generate_recipe_llm_post(self):
        test_prompt = "a quick pasta dish"
        response = self.app.post('/generate-recipe-llm', data={'prompt': test_prompt})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generate a New Recipe with AI', response.data) # Page title/header
        self.assertIn(b'AI Generated Recipe: AI Generated Pasta Dish', response.data) # Check for dummy recipe name
        self.assertIn(b'Pasta', response.data) # Check for some dummy ingredient
        self.assertIn(b'Cook pasta.', response.data) # Check for some dummy instruction
        # Check if the original prompt is displayed back on the page (e.g., in the form input)
        self.assertIn(test_prompt.encode('utf-8'), response.data)

    def test_generate_recipe_llm_post_empty_prompt(self):
        response = self.app.post('/generate-recipe-llm', data={'prompt': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generate a New Recipe with AI', response.data)
        # Check that no recipe is generated, or a specific message is shown
        # Current dummy implementation might still return a default AI recipe or based on empty string.
        # For now, we'll just check that it doesn't error out and the form is still there.
        self.assertNotIn(b'AI Generated Recipe:', response.data) # Assuming no recipe block if prompt is empty and handled.
                                                                # This might need adjustment based on actual LLM client behavior.

    def test_save_ai_recipe_form_redirect_and_prefill(self):
        # Simulate data that would come from the AI generation page
        ai_recipe_data = {
            "name": "AI Test Dish",
            "description": "A test dish from AI.",
            "ingredients": "AI Ingredient 1\nAI Ingredient 2",
            "instructions": "AI Step 1\nAI Step 2"
        }

        # Test the /save-ai-recipe-form redirect
        response_redirect = self.app.get(
            '/save-ai-recipe-form',
            query_string=ai_recipe_data,
            follow_redirects=False # We want to check the redirect location
        )
        self.assertEqual(response_redirect.status_code, 302) # Check for redirect

        # Check the path part of the redirect
        redirect_url_parsed = urlparse(response_redirect.location)
        # url_for might generate an absolute URL if SERVER_NAME is set,
        # but test client redirects might be path-relative.
        # We are primarily interested in the path and query parameters.
        expected_path = url_for('add_recipe')

        # Compare only the path component
        self.assertEqual(redirect_url_parsed.path, urlparse(expected_path).path)

        # Check query parameters from the redirect URL
        redirect_query_params = parse_qs(redirect_url_parsed.query)
        self.assertEqual(redirect_query_params.get('name', [''])[0], ai_recipe_data['name'])
        self.assertEqual(redirect_query_params.get('description', [''])[0], ai_recipe_data['description'])
        self.assertEqual(redirect_query_params.get('ingredients', [''])[0], ai_recipe_data['ingredients'])
        self.assertEqual(redirect_query_params.get('instructions', [''])[0], ai_recipe_data['instructions'])

        # Test that the add_recipe page is pre-filled when accessed with these params
        # Use follow_redirects=True on the initial GET to directly get the final page
        response_prefilled_form = self.app.get(
            '/save-ai-recipe-form',
            query_string=ai_recipe_data,
            follow_redirects=True
        )
        self.assertEqual(response_prefilled_form.status_code, 200)

        self.assertIn(b'value="AI Test Dish"', response_prefilled_form.data)
        self.assertIn(b'A test dish from AI.</textarea>', response_prefilled_form.data)
        self.assertIn(b'AI Ingredient 1\nAI Ingredient 2</textarea>', response_prefilled_form.data)
        self.assertIn(b'AI Step 1\nAI Step 2</textarea>', response_prefilled_form.data)

    def test_view_recipe_page(self):
        recipe = self._add_test_recipe(name="My Viewable Recipe", description="Desc for view", ingredients="View Ing 1\nView Ing 2", instructions="View Inst 1")
        response = self.app.get(url_for('view_recipe', recipe_id=recipe.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Viewable Recipe', response.data)
        self.assertIn(b'Desc for view', response.data)
        self.assertIn(b'View Ing 1\nView Ing 2', response.data)
        self.assertIn(b'View Inst 1', response.data)
        self.assertIn(b'Modify with AI', response.data) # Check for the new button

    def test_modify_recipe_llm_form_get(self):
        recipe = self._add_test_recipe(name="Recipe to Modify")
        response = self.app.get(url_for('modify_recipe_llm_form', recipe_id=recipe.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Modify Recipe with AI', response.data)
        self.assertIn(b'Original Recipe: Recipe to Modify', response.data)
        self.assertIn(b'How would you like to modify this recipe?', response.data)

    def test_submit_llm_modification_and_save(self):
        recipe = self._add_test_recipe(name="Chicken Soup", ingredients="Chicken\nNoodles\nBroth", description="A classic soup.", instructions="Boil it.")
        modification_prompt = "make it vegetarian"

        # Test submitting the modification
        response_modification = self.app.post(
            url_for('submit_llm_modification', recipe_id=recipe.id),
            data={'prompt': modification_prompt}
        )
        self.assertEqual(response_modification.status_code, 200)
        self.assertIn(b'AI Modified Recipe Suggestion', response_modification.data)
        self.assertIn(b'Chicken Soup (Vegetarian AI Remix)', response_modification.data) # Name changed by dummy LLM
        self.assertIn(b'Tofu', response_modification.data) # Chicken replaced by Tofu
        self.assertIn(b'Save This Modified Recipe', response_modification.data)

        # Extract the details of the modified recipe (this is a bit of a hack for testing the dummy output)
        # In a real scenario, the modified_recipe dict would be directly available if the route returned it,
        # or we'd parse the HTML more carefully. Here, we rely on the dummy output structure.
        modified_name = "Chicken Soup (Vegetarian AI Remix)"
        modified_description = "A classic soup. Now with a vegetarian twist from our AI!"
        modified_ingredients = "Tofu\nNoodles\nBroth\n1 dash of AI Vegetarian Magic"
        modified_instructions = "Boil it.\nAI Chef's Note: Ensure all animal products are lovingly replaced with plant-based alternatives."

        ai_modified_recipe_data = {
            "name": modified_name,
            "description": modified_description,
            "ingredients": modified_ingredients,
            "instructions": modified_instructions
        }

        # Test the "Save This Modified Recipe" link leads to pre-filled add_recipe form
        response_prefilled_form = self.app.get(
            url_for('save_ai_recipe_form', **ai_modified_recipe_data), # Using the extracted/known modified data
            follow_redirects=True # This will follow the redirect from save_ai_recipe_form to add_recipe
        )
        self.assertEqual(response_prefilled_form.status_code, 200)
        self.assertIn(b'Add Recipe', response_prefilled_form.data) # Title of add_recipe page
        self.assertIn(b'value="Chicken Soup (Vegetarian AI Remix)"', response_prefilled_form.data)
        self.assertIn(b'A classic soup. Now with a vegetarian twist from our AI!</textarea>', response_prefilled_form.data)
        self.assertIn(b'Tofu\nNoodles\nBroth\n1 dash of AI Vegetarian Magic</textarea>', response_prefilled_form.data)
        self.assertIn(b'Boil it.\nAI Chef&#39;s Note: Ensure all animal products are lovingly replaced with plant-based alternatives.</textarea>', response_prefilled_form.data) # Note &#39; for apostrophe

    def test_profile_page(self):
        response = self.app.get('/profile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User Profile', response.data)
        self.assertIn(b'Dietary Preferences:', response.data) # Check for form label
        self.assertIn(b'Save Preferences', response.data) # Check for save button

if __name__ == '__main__':
    unittest.main()
