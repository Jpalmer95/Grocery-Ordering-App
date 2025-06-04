from flask import render_template, request, redirect, url_for, abort, flash # Added flash
from flask_login import login_required, current_user
from app import app, db
from app.models import Recipe, UserSettings
from app.llm_service import llm_client
# Removed: from .utils import get_available_llm_providers

@app.route('/')
def index():
    return render_template('home.html', title='Home') # Publicly accessible

@app.route('/recipes')
@login_required
def recipes():
    all_recipes = Recipe.query.all()
    return render_template('recipes.html', title='Recipes', recipes=all_recipes)

@app.route('/recipe/add', methods=['GET', 'POST'])
@login_required
def add_recipe():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        ingredients = request.form.get('ingredients')
        instructions = request.form.get('instructions')

        if name and ingredients and instructions: # Basic validation
            new_recipe = Recipe(
                name=name,
                description=description,
                ingredients=ingredients,
                instructions=instructions
            )
            db.session.add(new_recipe)
            db.session.commit()
            # Add flash message for success if implemented
            return redirect(url_for('recipes'))
        else:
            # Add flash message for error if implemented
            pass # Stay on the add recipe page, potentially with an error message
    # For GET request, check for query parameters for pre-filling
    name = request.args.get('name')
    description = request.args.get('description')
    ingredients = request.args.get('ingredients')
    instructions = request.args.get('instructions')
    return render_template('add_recipe.html', title='Add Recipe',
                           name=name, description=description,
                           ingredients=ingredients, instructions=instructions)

@app.route('/recipe/<int:recipe_id>')
@login_required
def view_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)
    return render_template('view_recipe.html', recipe=recipe)

@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)
    if request.method == 'POST':
        recipe.name = request.form.get('name', recipe.name)
        recipe.description = request.form.get('description', recipe.description)
        recipe.ingredients = request.form.get('ingredients', recipe.ingredients)
        recipe.instructions = request.form.get('instructions', recipe.instructions)
        db.session.commit()
        # Add flash message for success if implemented
        return redirect(url_for('recipes'))
    return render_template('edit_recipe.html', title='Edit Recipe', recipe=recipe)

@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
def delete_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)
    db.session.delete(recipe)
    db.session.commit()
    # Add flash message for success if implemented
    return redirect(url_for('recipes'))

@app.route('/grocery-list')
@login_required # Assuming grocery list is user-specific or requires login
def grocery_list():
    # This page will now primarily be rendered by generate_grocery_list
    # or could show a default empty state / previously generated list (if persisted)
    return render_template('grocery_list.html', title='Grocery List', ingredients=None)

# This will be the target for the form in recipes.html
@app.route('/generate-grocery-list', methods=['POST'])
@login_required
def generate_grocery_list():
    aggregated_ingredients = []
    recipe_ids = request.form.getlist('recipe_ids')
    if not recipe_ids:
        # Handle case with no recipes selected, maybe flash a message
        return redirect(url_for('recipes')) # Or render grocery_list with a message

    selected_recipes = Recipe.query.filter(Recipe.id.in_(recipe_ids)).all()
    ingredient_counts = {} # Using a dict to count ingredient occurrences

    for recipe in selected_recipes:
        ingredients_list = [ing.strip().lower() for ing in recipe.ingredients.split('\n') if ing.strip()]
        for ingredient in ingredients_list:
            ingredient_counts[ingredient] = ingredient_counts.get(ingredient, 0) + 1

    # Format for display: "Ingredient (Count)" if count > 1
    formatted_ingredients = []
    for ingredient, count in sorted(ingredient_counts.items()):
        if count > 1:
            formatted_ingredients.append(f"{ingredient.capitalize()} (x{count})")
        else:
            formatted_ingredients.append(ingredient.capitalize())

    return render_template('grocery_list.html', title='Generated Grocery List', ingredients=formatted_ingredients)

@app.route('/order-instacart', methods=['POST'])
@login_required
def order_with_instacart():
    ingredients = request.form.getlist('ingredients')
    # The ingredients are already formatted (e.g., "Cheese (x2)") from the generate_grocery_list step
    # If raw ingredients were needed, logic to re-process or fetch them would be here.
    if not ingredients:
        # Handle case where no ingredients are submitted, perhaps redirect or show error
        # For now, just pass empty list to template, it will show a message.
        pass
    return render_template('order_instacart.html', title='Order with InstaCart', ingredients=ingredients)

@app.route('/generate-recipe-llm', methods=['GET', 'POST'])
@login_required
def generate_recipe_llm():
    user_settings = current_user.settings
    available_providers = [{'value': 'placeholder', 'name': 'Placeholder (No API Key Needed)', 'configured': True}]
    api_keys = {}

    if user_settings:
        if user_settings.gemini_api_key:
            available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': True})
            api_keys['gemini'] = user_settings.gemini_api_key
        else:
            available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': False})
        if user_settings.hugging_face_api_key:
            available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': True})
            api_keys['hugging_face'] = user_settings.hugging_face_api_key
        else:
            available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': False})
    else: # No user_settings record yet
        available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': False})
        available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': False})

    prompt_text = request.form.get('prompt') if request.method == 'POST' else request.args.get('prompt')
    selected_provider = request.form.get('provider') if request.method == 'POST' else "placeholder"
    generated_recipe_data = None
    error_message = None
    error_details = None

    if request.method == 'POST':
        if prompt_text:
            # Ensure the selected provider's key is actually available if not placeholder
            if selected_provider != 'placeholder' and not api_keys.get(selected_provider):
                error_message = f"API key for {selected_provider.replace('_', ' ').title()} not found in your settings."
            else:
                print(f"Route 'generate_recipe_llm': User selected provider '{selected_provider}' with prompt: '{prompt_text}'")
                llm_response = llm_client.generate_recipe(prompt_text, provider=selected_provider, api_keys=api_keys)
                if isinstance(llm_response, dict) and 'error' in llm_response:
                    error_message = llm_response['error']
                    error_details = llm_response.get('details')
                    generated_recipe_data = {k: v for k, v in llm_response.items() if k not in ['error', 'details']}
                    if not any(generated_recipe_data.values()):
                        generated_recipe_data = None
                else: # No error from LLM or not a dict (should be recipe data)
                    generated_recipe_data = llm_response
                    # error_message and error_details remain None if successful
        else:
            error_message = "Prompt cannot be empty."

    return render_template('generate_recipe_llm.html',
                           title='Generate Recipe with AI',
                           prompt=prompt_text,
                           generated_recipe=generated_recipe_data,
                           available_providers=available_providers,
                           selected_provider=selected_provider,
                           error_message=error_message,
                           error_details=error_details)

@app.route('/recipe/<int:recipe_id>/modify-llm-form', methods=['GET'])
@login_required
def modify_recipe_llm_form(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)

    user_settings = current_user.settings
    available_providers = [{'value': 'placeholder', 'name': 'Placeholder (No API Key Needed)', 'configured': True}]
    if user_settings:
        if user_settings.gemini_api_key:
            available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': True})
        else:
            available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': False})
        if user_settings.hugging_face_api_key:
            available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': True})
        else:
            available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': False})
    else:
        available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': False})
        available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': False})

    return render_template('modify_recipe_llm.html',
                           title='Modify Recipe with AI',
                           original_recipe=recipe,
                           user_prompt=None,
                           modified_recipe=None,
                           available_providers=available_providers,
                           selected_provider="placeholder")

@app.route('/recipe/<int:recipe_id>/submit-llm-modification', methods=['POST'])
@login_required
def submit_llm_modification(recipe_id):
    original_recipe = db.session.get(Recipe, recipe_id)
    if not original_recipe:
        abort(404) # Should not happen if coming from the form correctly

    user_prompt = request.form.get('prompt')

    # For the dummy service, we can pass the original recipe data as a dict
    original_recipe_data = {
        "name": original_recipe.name, # Using actual DB data
        "description": original_recipe.description,
        "ingredients": original_recipe.ingredients,
        "instructions": original_recipe.instructions
    }

    modified_recipe_suggestion = None
    if user_prompt:
        user_settings = current_user.settings
        available_providers = [{'value': 'placeholder', 'name': 'Placeholder (No API Key Needed)', 'configured': True}]
        api_keys = {}
        if user_settings:
            if user_settings.gemini_api_key:
                available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': True})
                api_keys['gemini'] = user_settings.gemini_api_key
            else:
                available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': False})
            if user_settings.hugging_face_api_key:
                available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': True})
                api_keys['hugging_face'] = user_settings.hugging_face_api_key
            else:
                available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': False})
        else:
            available_providers.append({'value': 'gemini', 'name': 'Google Gemini', 'configured': False})
            available_providers.append({'value': 'hugging_face', 'name': 'Hugging Face (Mistral)', 'configured': False})

        selected_provider = request.form.get('provider', 'placeholder')

        if selected_provider != 'placeholder' and not api_keys.get(selected_provider):
            error_message = f"API key for {selected_provider.replace('_', ' ').title()} not found in your settings."
            modified_recipe_suggestion = None # Ensure no recipe is shown if key is missing for selected provider
        else:
            print(f"Route 'submit_llm_modification': User selected provider '{selected_provider}' for recipe ID {recipe_id} with prompt: '{user_prompt}'")
            llm_response = llm_client.modify_recipe(original_recipe_data, user_prompt, provider=selected_provider, api_keys=api_keys)
            if isinstance(llm_response, dict) and 'error' in llm_response:
                error_message = llm_response['error']
                error_details = llm_response.get('details')
                modified_recipe_suggestion = {k: v for k, v in llm_response.items() if k not in ['error', 'details']}
                if not any(modified_recipe_suggestion.values()):
                    modified_recipe_suggestion = None
            else: # No error from LLM
                modified_recipe_suggestion = llm_response
                error_message = None
                error_details = None
    else: # No user_prompt submitted
        # error_message and error_details remain as initialized (None)
        # modified_recipe_suggestion remains as initialized (None)
        # This case should ideally be caught by form validation if prompt is required
        pass

    return render_template('modify_recipe_llm.html',
                           title='Modify Recipe with AI',
                           original_recipe=original_recipe,
                           user_prompt=user_prompt, # The prompt user typed
                           modified_recipe=modified_recipe_suggestion, # The AI's output or None/partial on error
                           available_providers=available_providers,
                           selected_provider=selected_provider,
                           error_message=error_message,
                           error_details=error_details)

@app.route('/save-ai-recipe-form') # GET request
@login_required # This form leads to adding a recipe, should be protected
def save_ai_recipe_form():
    name = request.args.get('name')
    description = request.args.get('description')
    ingredients = request.args.get('ingredients')
    instructions = request.args.get('instructions')
    # Redirect to the add_recipe form, passing data as query parameters
    # This keeps the pre-filling logic consolidated in add_recipe's GET handler
    return redirect(url_for('add_recipe', name=name, description=description, ingredients=ingredients, instructions=instructions))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Placeholder user preferences data
    # Fetch settings related to the currently logged-in user
    user_settings = current_user.settings
    if not user_settings:
        # If no settings exist, create a new one for the current user
        user_settings = UserSettings(user_id=current_user.id)
        # Pass this new, unsaved instance to the template for GET.
        # It will be added and committed in POST if form is submitted.
        # Or, if we want to ensure it exists for GET display:
        # db.session.add(user_settings)
        # db.session.commit() # Commit to make it exist for GET
        # user_settings = current_user.settings # Re-fetch

    # Placeholder for dietary preferences - this would ideally also be in UserSettings or another model
    user_preferences = {
        'dietary_preferences': 'vegetarian',
        'family_size': 4
    }

    if request.method == 'POST':
        # Update dietary preferences (still placeholder)
        user_preferences['dietary_preferences'] = request.form.get('dietary_preferences', user_preferences['dietary_preferences'])
        user_preferences['family_size'] = int(request.form.get('family_size', user_preferences['family_size']))

        # Fetch or create UserSettings for the current user
        if not current_user.settings:
            current_user.settings = UserSettings(user_id=current_user.id)
            db.session.add(current_user.settings)

        hf_key = request.form.get('hugging_face_api_key')
        gemini_key = request.form.get('gemini_api_key')

        if hf_key:
            current_user.settings.hugging_face_api_key = hf_key
        elif 'hugging_face_api_key' in request.form: # Field was present but empty
            current_user.settings.hugging_face_api_key = None

        if gemini_key:
            current_user.settings.gemini_api_key = gemini_key
        elif 'gemini_api_key' in request.form: # Field was present but empty
            current_user.settings.gemini_api_key = None

        # Save Theme preference
        selected_theme = request.form.get('theme')
        if selected_theme and selected_theme in ['light', 'dark', 'system']:
            current_user.settings.theme = selected_theme

        # Save Dietary Restrictions
        restrictions_text = request.form.get('dietary_restrictions')
        current_user.settings.dietary_restrictions = restrictions_text.strip() if restrictions_text else None

        db.session.commit()
        flash("Profile settings saved successfully!", "success")
        return redirect(url_for('profile'))

    # For GET request, pass the loaded or new (unsaved if not committed above) user_settings
    return render_template('profile.html', title='Profile',
                           preferences=user_preferences,
                           user_settings=current_user.settings) # Pass current_user.settings directly
