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

import re

from py4web import URL, abort, action, redirect, request

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


# POST /api/posts - create a new post and store tags
@action("api/posts", method=["POST"])
@action.uses(db, auth.user)
def create_post():
    content = request.json.get("content")
    if not content:
        abort(400, "Missing content")

    # insert content
    post_id = db.post_item.insert(content=content)
    db.commit()

    # extract tags (without #)
    tags = set(re.findall(r"#(\w+)", content))
    for tag in tags:
        db.tag_item.insert(name=tag.lower(), post_item_id=post_id)
    db.commit()

    return {"id": post_id}


# GET /api/posts?tags=x,y,z - get posts filtered by tags
@action("api/posts", method=["GET"])
@action.uses(db, auth.user)
def get_posts():
    tag_query = request.query.get("tags")
    user_id = auth.user_id

    if tag_query:
        tag_list = tag_query.split(",")
        tag_rows = db(db.tag_item.name.belongs([t.lower() for t in tag_list])).select()
        post_ids = list({row.post_item_id for row in tag_rows})
        posts = db(db.post_item.id.belongs(post_ids)).select(orderby=~db.post_item.created_on, limitby=(0, 100))
    else:
        posts = db(db.post_item).select(orderby=~db.post_item.created_on, limitby=(0, 100))

    return {
        "posts": [
            {
                "id": post.id,
                "content": post.content,
                "created_on": post.created_on,
                "created_by": db.auth_user[post.created_by].username if db.auth_user[post.created_by] else "unknown",
                "can_delete": post.created_by == user_id,
            }
            for post in posts
        ]
    }


# DELETE /api/posts/<post_id> - delete a post
@action("api/posts/<post_id:int>", method=["DELETE"])
@action.uses(db, auth.user)
def delete_post(post_id):
    post = db.post_item(post_id)
    if not post or post.created_by != auth.user_id:
        abort(403)
    db(db.tag_item.post_item_id == post_id).delete()
    db(db.post_item.id == post_id).delete()
    return {"message": "Post deleted"}


# GET /api/tags - return all unique known tags
@action("api/tags", method=["GET"])
@action.uses(db, auth.user)
def get_tags():
    tags = db(db.tag_item).select(db.tag_item.name, distinct=True)
    tag_names = sorted(set(tag.name for tag in tags))
    return {"tags": tag_names}


# GET /api/ingredients?name=x - search ingredients by name
@action("api/ingredients", method=["GET"])
@action.uses(db, auth.user)
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
    recipes = db(db.recipes).select(orderby=~db.recipes.created_on)
    
    return {
        "recipes": [
            {
                "id": recipe.id,
                "name": recipe.name,
                "description": recipe.description,
                "instructions": recipe.instructions,
                "author": db.auth_user[recipe.author].username if db.auth_user[recipe.author] else "unknown",
                "created_on": recipe.created_on,
                "updated_on": recipe.updated_on,
                "ingredients": [
                    {
                        "ingredient_id": link.ingredient_id,
                        "quantity": link.quantity,
                        "name": db.ingredients[link.ingredient_id].name if db.ingredients[link.ingredient_id] else "Unknown"
                    }
                    for link in db(db.recipe_ingredients.recipe_id == recipe.id).select()
                ]
            }
            for recipe in recipes
        ]
    }


# POST /api/recipes - create a new recipe
@action("api/recipes", method=["POST"])
@action.uses(db, auth.user)
def create_recipe():
    data = request.json
    name = data.get("name")
    description = data.get("description")
    instructions = data.get("instructions")
    ingredients = data.get("ingredients", [])

    if not name:
        abort(400, "Recipe name is required")

    # Create the recipe
    recipe_id = db.recipes.insert(
        name=name,
        description=description,
        instructions=instructions,
        author=auth.user_id
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
