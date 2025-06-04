import unittest
from unittest.mock import patch, Mock, ANY
from flask import url_for, session
from flask_login import login_user, current_user as flask_login_current_user # To check auth state
from urllib.parse import urlparse, parse_qs
from app import app, db
from app.models import Recipe, UserSettings, User
from app.auth_routes import google_bp # Import the blueprint to connect the signal handler

class AppTestCase(unittest.TestCase):

    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SERVER_NAME'] = 'localhost.test'
        app.config['LOGIN_DISABLED'] = False

        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_test_user(self, email="test@example.com", name="Test User", google_id_suffix=""):
        gid = f"test_google_id_{email}{google_id_suffix}"
        user = User.query.filter_by(google_id=gid).first()
        if not user:
            user = User(email=email, name=name, google_id=gid)
            db.session.add(user)
            db.session.commit()
        return user

    def test_home_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome to My Recipe App!', response.data)
        self.assertIn(b'This is the home page.', response.data)

    @patch('flask_login.utils._get_user')
    def test_recipes_page(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.get('/recipes')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Recipes', response.data)
        self.assertIn(b'Add New Recipe', response.data)
        self.assertIn(b'No recipes found.', response.data)

    @patch('flask_login.utils._get_user')
    def test_add_recipe_page_get(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.get('/recipe/add')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Add a New Recipe', response.data)
        self.assertIn(b'Recipe Name:', response.data)

    @patch('flask_login.utils._get_user')
    def test_add_and_view_recipe(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response_post = self.client.post('/recipe/add', data=dict(
            name='Test Soup',
            description='A tasty test soup',
            ingredients='Water\nCarrots\nSalt',
            instructions='Boil water\nAdd carrots\nAdd salt'
        ), follow_redirects=True)
        self.assertEqual(response_post.status_code, 200)
        self.assertIn(b'Test Soup', response_post.data)
        self.assertIn(b'A tasty test soup', response_post.data)
        self.assertNotIn(b'No recipes found.', response_post.data)

        recipe = Recipe.query.filter_by(name='Test Soup').first()
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe.description, 'A tasty test soup')

        response_get_recipes = self.client.get('/recipes')
        self.assertEqual(response_get_recipes.status_code, 200)
        self.assertIn(b'Test Soup', response_get_recipes.data)
        self.assertIn(b'A tasty test soup', response_get_recipes.data)

    def _add_test_recipe(self, name="Default Recipe", description="Default Desc", ingredients="Default Ing", instructions="Default Inst"):
        recipe = Recipe(name=name, description=description, ingredients=ingredients, instructions=instructions)
        db.session.add(recipe)
        db.session.commit()
        return recipe

    @patch('flask_login.utils._get_user')
    def test_edit_recipe_get(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="Original Name")
        response = self.client.get(f'/recipe/{recipe.id}/edit')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Edit Recipe: Original Name', response.data)
        self.assertIn(b'Original Name', response.data)

    @patch('flask_login.utils._get_user')
    def test_edit_recipe_post(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="Old Name", description="Old Desc")
        response = self.client.post(f'/recipe/{recipe.id}/edit', data=dict(
            name='New Name',
            description='New Desc',
            ingredients=recipe.ingredients,
            instructions=recipe.instructions
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'New Name', response.data)
        self.assertIn(b'New Desc', response.data)
        self.assertNotIn(b'Old Name', response.data)

        updated_recipe = db.session.get(Recipe, recipe.id)
        self.assertEqual(updated_recipe.name, 'New Name')
        self.assertEqual(updated_recipe.description, 'New Desc')

    @patch('flask_login.utils._get_user')
    def test_delete_recipe(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="To Be Deleted")
        recipe_id = recipe.id

        response_get = self.client.get('/recipes')
        self.assertIn(b'To Be Deleted', response_get.data)

        response_post = self.client.post(f'/recipe/{recipe_id}/delete', follow_redirects=True)
        self.assertEqual(response_post.status_code, 200)
        self.assertNotIn(b'To Be Deleted', response_post.data)

        all_recipes_after_delete = Recipe.query.all()
        if not all_recipes_after_delete:
            self.assertIn(b'No recipes found.', response_post.data)
        else:
            self.assertNotIn(b'No recipes found.', response_post.data)

        deleted_recipe = db.session.get(Recipe, recipe_id)
        self.assertIsNone(deleted_recipe)

    @patch('flask_login.utils._get_user')
    def test_grocery_list_page(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.get('/grocery-list')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Grocery List', response.data)
        self.assertIn(b'Select recipes from the', response.data)

    @patch('flask_login.utils._get_user')
    def test_generate_grocery_list_no_selection(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.post('/generate-grocery-list', data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Recipes', response.data)

    @patch('flask_login.utils._get_user')
    def test_generate_grocery_list_with_selection(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe1 = self._add_test_recipe(name="Pasta Bake", ingredients="Pasta\nTomato Sauce\nCheese")
        recipe2 = self._add_test_recipe(name="Salad", ingredients="Lettuce\nTomato\nCucumber\nCheese")
        recipe3 = self._add_test_recipe(name="Bread", ingredients="Flour\nWater\nSalt\nYeast")

        selected_ids = [str(recipe1.id), str(recipe2.id)]
        response = self.client.post('/generate-grocery-list', data={'recipe_ids': selected_ids})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generated Grocery List', response.data)
        self.assertIn(b'Cheese (x2)', response.data)
        self.assertIn(b'Cucumber', response.data)
        self.assertIn(b'Lettuce', response.data)
        self.assertIn(b'Pasta', response.data)
        self.assertIn(b'Tomato', response.data)
        self.assertIn(b'Tomato sauce', response.data)
        self.assertNotIn(b'Flour', response.data)

    @patch('flask_login.utils._get_user')
    def test_generate_grocery_list_single_recipe(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="Simple Soup", ingredients="Broth\nCarrots\nCelery")
        selected_ids = [str(recipe.id)]
        response = self.client.post('/generate-grocery-list', data={'recipe_ids': selected_ids})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generated Grocery List', response.data)
        self.assertIn(b'Broth', response.data)
        self.assertIn(b'Carrots', response.data)
        self.assertIn(b'Celery', response.data)
        self.assertNotIn(b'(x', response.data)

    @patch('flask_login.utils._get_user')
    def test_order_with_instacart_flow(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="Test Dish", ingredients="Ingredient A (x2)\nIngredient B")
        formatted_ingredients_from_list_page = ["Ingredient A (x2)", "Ingredient B"]

        response = self.client.post('/order-instacart', data={'ingredients': formatted_ingredients_from_list_page})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Order with InstaCart (Simulated)', response.data)
        self.assertIn(b'Ingredient A (x2)', response.data)
        self.assertIn(b'Find on InstaCart', response.data)
        self.assertIn(b'Ingredient B', response.data)

    @patch('flask_login.utils._get_user')
    def test_order_with_instacart_no_ingredients(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.post('/order-instacart', data={'ingredients': []})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Order with InstaCart (Simulated)', response.data)
        self.assertIn(b'No ingredients were sent to order.', response.data)

    @patch('flask_login.utils._get_user')
    def test_generate_recipe_llm_get(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.get('/generate-recipe-llm')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generate a New Recipe with AI', response.data)
        self.assertIn(b'What kind of recipe would you like?', response.data)
        self.assertIn(b'Choose AI Provider:', response.data)
        self.assertIn(b'Placeholder (No API Key Needed)', response.data)

    @patch('flask_login.utils._get_user')
    def test_generate_recipe_llm_post_with_provider_selection(self, mock_get_user):
        user = self._create_test_user(email="llm_user@example.com", google_id_suffix="_llm_selection")
        mock_get_user.return_value = user
        test_prompt = "a quick pasta dish"

        response_placeholder = self.client.post('/generate-recipe-llm', data={
            'prompt': test_prompt,
            'provider': 'placeholder'
        })
        self.assertEqual(response_placeholder.status_code, 200)
        if test_prompt:
            self.assertIn(b'AI Generated Pasta Dish (Placeholder)', response_placeholder.data)
        self.assertIn(b'<option value="placeholder" selected', response_placeholder.data)

        mock_user_settings = UserSettings(user_id=user.id, hugging_face_api_key="fake_hf_key_for_test")
        db.session.add(mock_user_settings)
        db.session.commit()
        # user.settings = mock_user_settings # This line is tricky, relationship might not update immediately for current_user proxy
                                        # The route fetches fresh settings, so this direct assignment isn't needed for route test

        response_hf = self.client.post('/generate-recipe-llm', data={
            'prompt': test_prompt,
            'provider': 'hugging_face'
        })
        self.assertEqual(response_hf.status_code, 200)
        self.assertIn(b'<strong>Error:</strong> Hugging Face API Error', response_hf.data)
        self.assertIn(b'Details: Invalid API Key or unauthorized.</small>', response_hf.data)
        self.assertIn(b'<option value="hugging_face" selected', response_hf.data)
        self.assertNotIn(b'<h2>AI Generated Recipe', response_hf.data)

        if user.settings: # Cleanup
            db.session.delete(user.settings)
            db.session.commit()

    @patch('flask_login.utils._get_user')
    def test_generate_recipe_llm_post_empty_prompt(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        response = self.client.post('/generate-recipe-llm', data={'prompt': '', 'provider': 'placeholder'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Generate a New Recipe with AI', response.data)
        self.assertIn(b'<strong>Error:</strong> Prompt cannot be empty.', response.data)
        self.assertNotIn(b'<h2>AI Generated Recipe', response.data)

    def test_llm_service_parsing_error_display_generate(self):
        pass

    # --- Authentication Flow Tests ---
    @patch('requests.Session.get') # Corrected: Patch requests.Session.get which OAuth2Session uses
    def test_google_oauth_callback_new_user(self, mock_session_get):
        # Simulate a successful OAuth response from Google
        mock_user_info = {
            'sub': 'new_google_id_123',
            'email': 'new_user@example.com',
            'name': 'New Google User',
            'picture': 'http://example.com/new_pic.jpg'
        }
        mock_resp = Mock()
        mock_resp.ok = True
        mock_resp.json.return_value = mock_user_info
        mock_session_get.return_value = mock_resp

        # Simulate accessing the callback URL as if redirected by Google
        # We need to ensure the blueprint session is set up with a dummy token
        # so that blueprint.session.get in the callback doesn't fail early.
        # This is typically handled by Flask-Dance before the signal is sent.
        # For testing the callback directly, we can simulate this state.
        with self.client as c: # Use client to manage session
            with c.session_transaction() as http_session:
                http_session['google_oauth_token'] = {'access_token': 'dummy_test_token'}

            # Make a request to the authorized URL. Flask-Dance will then call our callback.
            # The URL is /auth/google_login/authorized (auth_bp prefix + google_bp prefix + /authorized)
            # Note: The actual blueprint.session.get call inside the callback is what's patched.
            response = c.get(url_for('auth_bp.google.authorized'), follow_redirects=False) # This hits the /authorized endpoint

        # Assertions
        mock_session_get.assert_called_once() # Verify that userinfo endpoint was called
        self.assertEqual(mock_session_get.call_args[0][0], "/oauth2/v3/userinfo")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(url_for('profile')))

        user = User.query.filter_by(google_id='new_google_id_123').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'new_user@example.com')
        self.assertEqual(user.name, 'New Google User')
        self.assertEqual(user.profile_pic_url, 'http://example.com/new_pic.jpg')

        # Check if user is logged in via Flask-Login
        with self.client as c: # New request with the established session
            # To check current_user, we need a request context where it's populated
            # One way is to access another protected route
            c.get(url_for('profile')) # Make a request to populate current_user
            self.assertTrue(flask_login_current_user.is_authenticated)
            self.assertEqual(flask_login_current_user.id, user.id)


    @patch('requests.Session.get') # Corrected patch target
    def test_google_oauth_callback_existing_google_id(self, mock_session_get):
        # Create existing user
        existing_user = self._create_test_user(
            email="existing@example.com",
            name="Existing User",
            google_id_suffix="_google_id_exists"
        )

        mock_user_info = {
            'sub': existing_user.google_id, # Use existing Google ID
            'email': 'updated_email@example.com', # Simulate email update from Google
            'name': 'Updated Google Name',
            'picture': 'http://example.com/updated_pic.jpg'
        }
        mock_resp = Mock(ok=True)
        mock_resp.json.return_value = mock_user_info
        mock_session_get.return_value = mock_resp

        with self.client as c:
            with c.session_transaction() as http_session:
                http_session['google_oauth_token'] = {'access_token': 'dummy_test_token'}
            response = c.get(url_for('auth_bp.google.authorized'), follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(url_for('profile')))

        updated_user = User.query.get(existing_user.id)
        self.assertEqual(updated_user.email, 'updated_email@example.com')
        self.assertEqual(updated_user.name, 'Updated Google Name')
        self.assertEqual(updated_user.profile_pic_url, 'http://example.com/updated_pic.jpg')
        self.assertEqual(User.query.count(), 1) # No new user created

    @patch('requests.Session.get') # Corrected patch target
    def test_google_oauth_callback_existing_email_link_google_id(self, mock_session_get):
        # Create user with email, no google_id
        existing_user_by_email = self._create_test_user(
            email="link_me@example.com",
            name="Link Me User",
            google_id_suffix="_to_be_linked" # This google_id won't be used for lookup initially
        )
        # Manually set google_id to None for this test scenario
        existing_user_by_email.google_id = None
        db.session.commit()

        new_google_id = "newly_linked_google_id_789"
        mock_user_info = {
            'sub': new_google_id,
            'email': existing_user_by_email.email, # Match existing email
            'name': 'Linked Google Name', # Potentially new name
            'picture': 'http://example.com/linked_pic.jpg'
        }
        mock_resp = Mock(ok=True)
        mock_resp.json.return_value = mock_user_info
        mock_requests_get.return_value = mock_resp

        with self.client as c:
            with c.session_transaction() as http_session:
                http_session['google_oauth_token'] = {'access_token': 'dummy_test_token'}
            response = c.get(url_for('auth_bp.google.authorized'), follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(url_for('profile')))

        linked_user = User.query.get(existing_user_by_email.id)
        self.assertEqual(linked_user.google_id, new_google_id)
        self.assertEqual(linked_user.name, 'Linked Google Name')
        self.assertEqual(linked_user.profile_pic_url, 'http://example.com/linked_pic.jpg')
        self.assertEqual(User.query.count(), 1) # No new user created

    # --- End Authentication Flow Tests ---

    def test_login_required_redirection(self):
        # Access a protected route without logging in
        response = self.client.get(url_for('profile'), follow_redirects=False)
        self.assertEqual(response.status_code, 302) # Should redirect
        # Check if it redirects to the Google login page
        # Expected URL: /auth/google_login/google (from auth_bp.google.login) then potentially to Google
        # The immediate redirect from Flask-Login will be to login_manager.login_view
        # Since SERVER_NAME is set, url_for will generate absolute URLs for its main part.
        # The test client produces a path-relative 'next' parameter.
        redirect_url_parsed = urlparse(response.location)
        expected_path_parsed = urlparse(url_for('auth_bp.google.login')) # Path part

        self.assertEqual(redirect_url_parsed.path, expected_path_parsed.path)

        redirect_query_params = parse_qs(redirect_url_parsed.query)
        self.assertEqual(redirect_query_params.get('next', [''])[0], url_for('profile', _external=False)) # Compare relative path of next

    @patch('flask_login.utils._get_user')
    def test_logout_functionality(self, mock_get_user):
        user = self._create_test_user(email="logout_user@example.com", google_id_suffix="_logout")
        mock_get_user.return_value = user # Simulate user is logged in

        # First, verify user is logged in by accessing a protected route
        response = self.client.get(url_for('profile'), follow_redirects=False)
        self.assertEqual(response.status_code, 200) # Should be accessible

        # Perform logout
        response_logout = self.client.get(url_for('auth_bp.logout'), follow_redirects=False)
        self.assertEqual(response_logout.status_code, 302)
        expected_redirect_url = url_for('index') # Should be absolute due to SERVER_NAME
        self.assertEqual(response_logout.location, expected_redirect_url)

        # Verify user is logged out by trying to access a protected route again
        # We need a new way to check current_user after logout, as the previous mock_get_user is for the initial login.
        # The easiest is to check if the protected route now redirects to login.
        # For this to work correctly without the previous mock interfering, it's better to
        # use the test client in a way that doesn't carry over the patched current_user state,
        # or reset the patch.
        # A simpler way: Flask-Login's logout_user() modifies the session. Subsequent requests
        # with the same client (which maintains session cookies) should reflect logged-out state.

        # After logout, current_user should be anonymous.
        # We can check this by making a request and inspecting current_user in a route,
        # or by checking if a protected route now redirects.
        mock_get_user.return_value = None # Simulate no user found by user_loader for next request
                                          # This effectively means current_user will be AnonymousUserMixin

        response_after_logout = self.client.get(url_for('profile'), follow_redirects=False)
        self.assertEqual(response_after_logout.status_code, 302)
        expected_login_url_after_logout = url_for('auth_bp.google.login', next=url_for('profile'))
        self.assertEqual(response_after_logout.location, expected_login_url_after_logout)


    @patch('flask_login.utils._get_user')
    def test_save_ai_recipe_form_redirect_and_prefill(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        ai_recipe_data = {
            "name": "AI Test Dish",
            "description": "A test dish from AI.",
            "ingredients": "AI Ingredient 1\nAI Ingredient 2",
            "instructions": "AI Step 1\nAI Step 2"
        }

        response_redirect = self.client.get(
            '/save-ai-recipe-form',
            query_string=ai_recipe_data,
            follow_redirects=False
        )
        self.assertEqual(response_redirect.status_code, 302)

        redirect_url_parsed = urlparse(response_redirect.location)
        expected_path = url_for('add_recipe')

        self.assertEqual(redirect_url_parsed.path, urlparse(expected_path).path)

        redirect_query_params = parse_qs(redirect_url_parsed.query)
        self.assertEqual(redirect_query_params.get('name', [''])[0], ai_recipe_data['name'])
        self.assertEqual(redirect_query_params.get('description', [''])[0], ai_recipe_data['description'])
        self.assertEqual(redirect_query_params.get('ingredients', [''])[0], ai_recipe_data['ingredients'])
        self.assertEqual(redirect_query_params.get('instructions', [''])[0], ai_recipe_data['instructions'])

        response_prefilled_form = self.client.get(
            '/save-ai-recipe-form',
            query_string=ai_recipe_data,
            follow_redirects=True
        )
        self.assertEqual(response_prefilled_form.status_code, 200)

        self.assertIn(b'value="AI Test Dish"', response_prefilled_form.data)
        self.assertIn(b'A test dish from AI.</textarea>', response_prefilled_form.data)
        self.assertIn(b'AI Ingredient 1\nAI Ingredient 2</textarea>', response_prefilled_form.data)
        self.assertIn(b'AI Step 1\nAI Step 2</textarea>', response_prefilled_form.data)

    @patch('flask_login.utils._get_user')
    def test_view_recipe_page(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="My Viewable Recipe", description="Desc for view", ingredients="View Ing 1\nView Ing 2", instructions="View Inst 1")
        response = self.client.get(url_for('view_recipe', recipe_id=recipe.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Viewable Recipe', response.data)
        self.assertIn(b'Desc for view', response.data)
        self.assertIn(b'View Ing 1\nView Ing 2', response.data)
        self.assertIn(b'View Inst 1', response.data)
        self.assertIn(b'Modify with AI', response.data)

    @patch('flask_login.utils._get_user')
    def test_modify_recipe_llm_form_get(self, mock_get_user):
        user = self._create_test_user()
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="Recipe to Modify")
        response = self.client.get(url_for('modify_recipe_llm_form', recipe_id=recipe.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Modify Recipe with AI', response.data)
        self.assertIn(b'Original Recipe: Recipe to Modify', response.data)
        self.assertIn(b'How would you like to modify this recipe?', response.data)
        self.assertIn(b'Choose AI Provider:', response.data)

    @patch('flask_login.utils._get_user')
    def test_submit_llm_modification_and_save(self, mock_get_user):
        user = self._create_test_user(email="llm_mod_user@example.com", google_id_suffix="_llm_mod")
        mock_get_user.return_value = user
        recipe = self._add_test_recipe(name="Chicken Soup", ingredients="Chicken\nNoodles\nBroth", description="A classic soup.", instructions="Boil it.")
        modification_prompt = "make it vegetarian"

        response_modification = self.client.post(
            url_for('submit_llm_modification', recipe_id=recipe.id),
            data={'prompt': modification_prompt, 'provider': 'placeholder'}
        )
        self.assertEqual(response_modification.status_code, 200)
        self.assertIn(b'AI Modified Recipe Suggestion', response_modification.data)
        self.assertIn(b'Chicken Soup (Vegetarian AI Remix - Placeholder)', response_modification.data)
        self.assertIn(b'Tofu', response_modification.data)
        self.assertIn(b'AI Chef&#39;s Note', response_modification.data)
        self.assertIn(b'Save This Modified Recipe', response_modification.data)
        self.assertIn(b'<option value="placeholder" selected', response_modification.data)
        self.assertNotIn(b'alert-danger', response_modification.data)

        mock_user_settings_gemini = UserSettings(user_id=user.id, gemini_api_key="fake_gemini_key_for_test")
        db.session.add(mock_user_settings_gemini)
        db.session.commit()
        # user.settings = mock_user_settings_gemini # Not needed, route re-fetches

        with patch('app.routes.current_user', user):
            response_gemini_mod = self.client.post(
                url_for('submit_llm_modification', recipe_id=recipe.id),
                data={'prompt': modification_prompt, 'provider': 'gemini'}
            )
        self.assertEqual(response_gemini_mod.status_code, 200)
        self.assertIn(b'<strong>Error:</strong> Gemini API Error', response_gemini_mod.data)
        self.assertIn(b'Details: Invalid API Key provided.</small>', response_gemini_mod.data)
        self.assertIn(b'<option value="gemini" selected', response_gemini_mod.data)
        self.assertNotIn(b'Save This Modified Recipe', response_gemini_mod.data)
        self.assertNotIn(b'<h2>AI Modified Recipe Suggestion', response_gemini_mod.data)

        if user.settings:
            db.session.delete(user.settings)
            db.session.commit()

        modified_name = "Chicken Soup (Vegetarian AI Remix - Placeholder)"
        original_description = "A classic soup."
        modified_description = original_description + " Now with a vegetarian twist from our AI!"
        modified_ingredients = "Tofu\nNoodles\nBroth\n1 dash of AI Vegetarian Magic"
        modified_instructions = "Boil it.\nAI Chef's Note: Ensure all animal products are lovingly replaced with plant-based alternatives."

        ai_modified_recipe_data = {
            "name": modified_name,
            "description": modified_description,
            "ingredients": modified_ingredients,
            "instructions": modified_instructions
        }

        response_prefilled_form = self.client.get(
            url_for('save_ai_recipe_form', **ai_modified_recipe_data),
            follow_redirects=True
        )
        self.assertEqual(response_prefilled_form.status_code, 200)
        self.assertIn(b'Add Recipe', response_prefilled_form.data)
        self.assertIn(b'value="Chicken Soup (Vegetarian AI Remix - Placeholder)"', response_prefilled_form.data)
        self.assertIn(b'A classic soup. Now with a vegetarian twist from our AI!</textarea>', response_prefilled_form.data)
        self.assertIn(b'Tofu\nNoodles\nBroth\n1 dash of AI Vegetarian Magic</textarea>', response_prefilled_form.data)
        self.assertIn(b'Boil it.\nAI Chef&#39;s Note: Ensure all animal products are lovingly replaced with plant-based alternatives.</textarea>', response_prefilled_form.data)

    @patch('flask_login.utils._get_user')
    def test_profile_page(self, mock_get_user):
        user = self._create_test_user(email="profile_user@example.com", google_id_suffix="_profile")
        mock_get_user.return_value = user

        response = self.client.get('/profile')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User Profile', response.data)
        self.assertIn(b'Hugging Face API Key:', response.data)
        self.assertIn(b'Google Gemini API Key:', response.data)
        self.assertIn(b'Site Theme', response.data)
        self.assertIn(b'Dietary Restrictions (comma-separated)', response.data)
        self.assertIn(b'InstaCart API Key (Future)', response.data) # Placeholder
        self.assertIn(b'Favor API Key (Future)', response.data) # Placeholder
        self.assertIn(b'Save All Settings', response.data)

        # Check for disabled attribute on placeholder inputs
        self.assertIn(b'id="instacart_api_key" name="instacart_api_key" placeholder="InstaCart integration coming soon" disabled', response.data)
        self.assertIn(b'id="favor_api_key" name="favor_api_key" placeholder="Favor integration coming soon" disabled', response.data)


        if user.settings:
            db.session.delete(user.settings)
            db.session.commit()
            user = db.session.get(User, user.id)

        hf_test_key = "hf_test_12345_profile"
        gemini_test_key = "gemini_test_67890_profile"
        test_restrictions = "vegetarian, gluten-free"

        response_post = self.client.post('/profile', data=dict(
            dietary_preferences='vegan',
            family_size='2',
            hugging_face_api_key=hf_test_key,
            gemini_api_key=gemini_test_key,
            theme='dark',
            dietary_restrictions=test_restrictions # Add to POST
        ), follow_redirects=True)

        self.assertEqual(response_post.status_code, 200)
        self.assertIn(f'value="{hf_test_key}"'.encode('utf-8'), response_post.data)
        self.assertIn(f'value="{gemini_test_key}"'.encode('utf-8'), response_post.data)
        self.assertIn(b'<option value="dark" selected', response_post.data)
        self.assertIn(b'<html lang="en" data-theme="dark">', response_post.data)
        self.assertIn(test_restrictions.encode('utf-8'), response_post.data) # Check restrictions displayed

        self.assertIsNotNone(user.settings)
        self.assertEqual(user.settings.hugging_face_api_key, hf_test_key)
        self.assertEqual(user.settings.gemini_api_key, gemini_test_key)
        self.assertEqual(user.settings.theme, 'dark')
        self.assertEqual(user.settings.dietary_restrictions, test_restrictions)

        # Test clearing a key, changing theme, and clearing restrictions
        response_clear_all = self.client.post('/profile', data=dict(
            dietary_preferences='vegan', family_size='2',
            hugging_face_api_key='',
            gemini_api_key=gemini_test_key,
            theme='system',
            dietary_restrictions='' # Clear restrictions
        ), follow_redirects=True)
        self.assertEqual(response_clear_all.status_code, 200)

        self.assertIsNone(user.settings.hugging_face_api_key)
        self.assertEqual(user.settings.gemini_api_key, gemini_test_key)
        self.assertEqual(user.settings.theme, 'system')
        self.assertIsNone(user.settings.dietary_restrictions) # Check restrictions cleared

        self.assertNotIn(f'value="{hf_test_key}"'.encode('utf-8'), response_clear_all.data)
        self.assertIn(f'value="{gemini_test_key}"'.encode('utf-8'), response_clear_all.data)
        self.assertIn(b'<option value="system" selected', response_clear_all.data)
        self.assertNotIn(b'data-theme=', response_clear_all.data)
        # Check that the textarea for restrictions is empty
        self.assertIn(b'<textarea class="form-control" id="dietary_restrictions" name="dietary_restrictions" rows="3"></textarea>', response_clear_all.data)


if __name__ == '__main__':
    unittest.main()
