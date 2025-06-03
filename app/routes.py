from flask import render_template, request, redirect, url_for, abort
from app import app, db
from app.models import Recipe
from app.llm_service import llm_client # Import the LLM client

@app.route('/')
def index():
    return render_template('home.html', title='Home')

@app.route('/recipes')
def recipes():
    all_recipes = Recipe.query.all()
    return render_template('recipes.html', title='Recipes', recipes=all_recipes)

@app.route('/recipe/add', methods=['GET', 'POST'])
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
def view_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)
    return render_template('view_recipe.html', recipe=recipe)

@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
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
def delete_recipe(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)
    db.session.delete(recipe)
    db.session.commit()
    # Add flash message for success if implemented
    return redirect(url_for('recipes'))

@app.route('/grocery-list') # Kept simple for now
def grocery_list():
    # This page will now primarily be rendered by generate_grocery_list
    # or could show a default empty state / previously generated list (if persisted)
    return render_template('grocery_list.html', title='Grocery List', ingredients=None) # Pass None or an empty list

# This will be the target for the form in recipes.html
@app.route('/generate-grocery-list', methods=['POST'])
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
def generate_recipe_llm():
    prompt = None
    generated_recipe = None
    if request.method == 'POST':
        prompt = request.form.get('prompt')
        if prompt:
            # In a real app, you might want to handle potential errors from the LLM service
            generated_recipe = llm_client.generate_recipe(prompt)
        else:
            # Handle empty prompt, maybe flash a message
            pass
    return render_template('generate_recipe_llm.html', title='Generate Recipe with AI', prompt=prompt, generated_recipe=generated_recipe)

@app.route('/recipe/<int:recipe_id>/modify-llm-form', methods=['GET'])
def modify_recipe_llm_form(recipe_id):
    recipe = db.session.get(Recipe, recipe_id)
    if not recipe:
        abort(404)
    return render_template('modify_recipe_llm.html', title='Modify Recipe with AI', original_recipe=recipe, user_prompt=None, modified_recipe=None)

@app.route('/recipe/<int:recipe_id>/submit-llm-modification', methods=['POST'])
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
        modified_recipe_suggestion = llm_client.modify_recipe(original_recipe_data, user_prompt)

    return render_template('modify_recipe_llm.html',
                           title='Modify Recipe with AI',
                           original_recipe=original_recipe, # Pass original from DB for display
                           user_prompt=user_prompt,
                           modified_recipe=modified_recipe_suggestion)

@app.route('/save-ai-recipe-form') # GET request
def save_ai_recipe_form():
    name = request.args.get('name')
    description = request.args.get('description')
    ingredients = request.args.get('ingredients')
    instructions = request.args.get('instructions')
    # Redirect to the add_recipe form, passing data as query parameters
    # This keeps the pre-filling logic consolidated in add_recipe's GET handler
    return redirect(url_for('add_recipe', name=name, description=description, ingredients=ingredients, instructions=instructions))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    # Placeholder user preferences data
    user_preferences = {
        'dietary_preferences': 'vegetarian',
        'family_size': 4
    }
    if request.method == 'POST':
        # In a real app, you would save the form data here
        # For now, we can just get the submitted data and pass it back
        user_preferences['dietary_preferences'] = request.form.get('dietary_preferences', user_preferences['dietary_preferences'])
        user_preferences['family_size'] = int(request.form.get('family_size', user_preferences['family_size']))
        # Optionally, add a flash message here indicating success
    return render_template('profile.html', title='Profile', preferences=user_preferences)
