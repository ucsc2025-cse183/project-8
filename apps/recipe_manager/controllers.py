"""
This file defines actions, i.e. functions the URLs are mapped into
The @action(path) decorator exposes the function at URL:

    http://127.0.0.1:8000/{app_name}/{path}

If app_name == '_default' then simply

    http://127.0.0.1:8000/{path}

If path == 'index' it can be omitted:

    http://127.0.0.1:8000/

The path follows the bottlepy syntax.

@action.uses('generic.html')  indicates that the action uses the generic.html template
@action.uses(session)         indicates that the action uses the session
@action.uses(db)              indicates that the action uses the db
@action.uses(T)               indicates that the action uses the i18n & pluralization
@action.uses(auth.user)       indicates that the action requires a logged in user
@action.uses(auth)            indicates that the action requires the auth object

session, db, T, auth, and templates are examples of Fixtures.
Warning: Fixtures MUST be declared with @action.uses({fixtures}) else your app will result in undefined behavior
"""

import re, json, os, mimetypes

from py4web import URL, abort, action, redirect, request, HTTP

from .private.populate_recipes import import_recipes

from . import settings

from .common import (
    T,
    auth,
    authenticated,
    cache,
    db,
    flash,
    logger,
    session,
    unauthenticated,
)


@action("index")
@action.uses("index.html", auth.user)
def index():
    return {}

# GET /api/ingredients?name=x - search ingredients by name
@action("api/ingredients", method=["GET"])
@action.uses(db)
def get_ingredients():
    name_query = request.query.get("name")

    if name_query:
        # Case-insensitive search for ingredient name containing the query
        ingredients = db(db.ingredients.name.ilike("%%%s%%" % name_query)).select()
    else:
        # Return all ingredients if no name query is provided
        ingredients = db(db.ingredients).select()

    return {
        "ingredients": [
            {
                "id": ingredient.id,
                "name": ingredient.name,
                "unit": ingredient.unit,
                "calories_per_unit": ingredient.calories_per_unit,
                "description": ingredient.description,
            }
            for ingredient in ingredients
        ]
    }


# POST /api/ingredients - add a new ingredient
@action("api/ingredients", method=["POST"])
@action.uses(db, auth.user)
def add_ingredient():
    data = request.json
    name = data.get("name")
    unit = data.get("unit")
    calories_per_unit = data.get("calories_per_unit")
    description = data.get("description")

    if not name:
        abort(400, "Ingredient name is required.")

    # Check if an ingredient with the same name already exists (case-insensitive)
    existing_ingredient = db(db.ingredients.name.ilike(name)).select().first()
    if existing_ingredient:
        abort(409, "An ingredient with this name already exists.") # 409 Conflict

    ingredient_id = db.ingredients.insert(
        name=name,
        unit=unit,
        calories_per_unit=calories_per_unit,
        description=description
    )
    db.commit()

    return {"id": ingredient_id, "message": "Ingredient added successfully."}


# GET /api/recipes - get all recipes
@action("api/recipes", method=["GET"])
@action.uses(db, auth.user)
def get_recipes():
    name_query = request.params.get("name", "").strip()
    type_query = request.params.get("type", "").strip()
    query = db.recipes.id > 0
    if name_query:
        query &= db.recipes.name.ilike(f"%{name_query}%")
    if type_query:
        query &= db.recipes.type == type_query
    recipes = db(query).select(orderby=~db.recipes.created_on)
    return {
        "recipes": [
            {
                "id": recipe.id,
                "name": recipe.name,
                "type": recipe.type,
                "description": recipe.description,
                "instructions": recipe.instructions,
                "author": db.auth_user[recipe.author].username if db.auth_user[recipe.author] else "unknown",
                "created_on": recipe.created_on,
                "updated_on": recipe.updated_on,
                "total_calories": sum(
                    (link.quantity * db.ingredients[link.ingredient_id].calories_per_unit)
                    for link in db(db.recipe_ingredients.recipe_id == recipe.id).select()
                    if db.ingredients[link.ingredient_id] and db.ingredients[link.ingredient_id].calories_per_unit
                ),
                "ingredients": [
                    {
                        "ingredient_id": link.ingredient_id,
                        "quantity": link.quantity,
                        "name": db.ingredients[link.ingredient_id].name if db.ingredients[link.ingredient_id] else "Unknown",
                        "calories": (link.quantity * db.ingredients[link.ingredient_id].calories_per_unit) 
                            if db.ingredients[link.ingredient_id] and db.ingredients[link.ingredient_id].calories_per_unit else None
                    }
                    for link in db(db.recipe_ingredients.recipe_id == recipe.id).select()
                ],
                "image": recipe.image
            }
            for recipe in recipes
        ]
    }


# POST /api/recipes - create a new recipe
@action("api/recipes", method=["POST"])
@action.uses(db, auth.user)
def create_recipe():
    data = request.forms
    files = request.files

    name = data.get("name")
    type_ = data.get("type", "")
    description = data.get("description")
    instructions = data.get("instructions")
    ingredientsJson = data.get("ingredients")

    try:
        ingredients = json.loads(ingredientsJson) if ingredientsJson else []
    except json.JSONDecodeError:
        abort(400, "Invalid JSON in ingredients field")

    if not name:
        abort(400, "Recipe name is required")
    if not type_:
        abort(400, "Recipe type is required")

    # Image upload
    image = files.get("image")
    imageName = None
    if image:
        imageName = db.recipes.image.store(image.file, image.filename, path=settings.UPLOAD_FOLDER)

    # Create the recipe
    recipe_id = db.recipes.insert(
        name=name,
        type=type_,
        description=description,
        instructions=instructions,
        author=auth.user_id,
        image = imageName
    )

    # Add ingredients
    for ingredient in ingredients:
        if not ingredient.get("id") or ingredient.get("quantity") is None:
            db.rollback()
            abort(400, "Invalid ingredient data")
        
        db.recipe_ingredients.insert(
            recipe_id=recipe_id,
            ingredient_id=ingredient["id"],
            quantity=ingredient["quantity"]
        )

    db.commit()
    return {"id": recipe_id, "message": "Recipe created successfully"}


# PUT /api/recipes/<recipe_id> - update a recipe
@action("api/recipes/<recipe_id:int>", method=["PUT"])
@action.uses(db, auth.user)
def update_recipe(recipe_id):
    recipe = db.recipes(recipe_id)
    if not recipe or recipe.author != auth.user_id:
        abort(403, "Not authorized to update this recipe")

    data = request.json
    name = data.get("name")
    description = data.get("description")
    instructions = data.get("instructions")
    ingredients = data.get("ingredients", [])

    if not name:
        abort(400, "Recipe name is required")

    # Update recipe
    recipe.update_record(
        name=name,
        description=description,
        instructions=instructions
    )

    # Remove old ingredients
    db(db.recipe_ingredients.recipe_id == recipe_id).delete()

    # Add new ingredients
    for ingredient in ingredients:
        if not ingredient.get("id") or ingredient.get("quantity") is None:
            db.rollback()
            abort(400, "Invalid ingredient data")
        
        db.recipe_ingredients.insert(
            recipe_id=recipe_id,
            ingredient_id=ingredient["id"],
            quantity=ingredient["quantity"]
        )

    db.commit()
    return {"message": "Recipe updated successfully"}


# DELETE /api/recipes/<recipe_id> - delete a recipe
@action("api/recipes/<recipe_id:int>", method=["DELETE"])
@action.uses(db, auth.user)
def delete_recipe(recipe_id):
    recipe = db.recipes(recipe_id)
    if not recipe or recipe.author != auth.user_id:
        abort(403, "Not authorized to delete this recipe")

    # Delete recipe ingredients first (due to foreign key constraint)
    db(db.recipe_ingredients.recipe_id == recipe_id).delete()
    # Delete the recipe
    db(db.recipes.id == recipe_id).delete()
    db.commit()

    return {"message": "Recipe deleted successfully"}


# POST api/recipes/<recipe_id>/image - upload an image for a recipe
@action("api/recipes/<recipe_id:int>/image", method=["POST"])
@action.uses(db, auth.user)
def upload_recipe_image(recipe_id):
    recipe = db.recipes(recipe_id)

    if not recipe:
        abort(404, "Recipe not found.")

    if recipe.author != db.auth_user(auth.user_id).username:
        abort(403, "You do not have permission to upload an image for this recipe.")
    
    if "image" not in request.files:
            abort(400, "No image file provided.")

    # Update the recipe with the image
    recipe.update_record(image=request.files["image"])
    db.commit()

    return {"message": "Image uploaded successfully.", "image_url": recipe.image}

# populate database with TheMealDB API
@action("populate_recipes")
@action.uses(db)
def populate_recipes_action():
    import_recipes(db)
    return "Recipes successfully imported from TheMealDB API."

@action("all_recipes")
@action.uses("all_recipes.html", auth.user)
def all_recipes():
    return {}

@action("all_ingredients")
@action.uses("all_ingredients.html", auth.user)
def all_ingredients():
    return {}

@action("api/current_user", method=["GET"])
@action.uses(auth.user)
def get_current_user():
    user = auth.get_user()
    return {"username": user.get("username") if user else None}
