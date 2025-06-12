import requests

def import_recipes(db):
    print("Starting import_recipes")
    """ if db(db.recipes.id > 0).count() > 0:
        print("Recipes already exist in the database.")
        return """

    print("Fetching recipes from TheMealDB API...")
    url = "https://www.themealdb.com/api/json/v1/1/search.php?s="
    res = requests.get(url)

    if res.status_code != 200:
        print("Failed to fetch data from API.")
        return

    meals = res.json().get("meals", [])
    if not meals:
        print("No meals found.")
        return

    for meal in meals:
        recipe_id = db.recipes.insert(
            name=meal["strMeal"],
            description=meal.get("strCategory", ""),
            instructions=meal.get("strInstructions", ""),
            author=None
        )

        for i in range(1, 21):
            ing_name = meal.get(f"strIngredient{i}")
            ing_qty = meal.get(f"strMeasure{i}")

            if not ing_name or ing_name.strip() == "":
                continue

            existing = db(db.ingredients.name == ing_name.strip()).select().first()
            if existing:
                ing_id = existing.id
            else:
                ing_id = db.ingredients.insert(
                    name=ing_name.strip(),
                    unit="",
                    calories_per_unit=None,
                    description=""
                )

            db.recipe_ingredients.insert(
                recipe_id=recipe_id,
                ingredient_id=ing_id,
                quantity=parse_quantity(ing_qty)
            )

    db.commit()
    print(f"Imported {len(meals)} recipes.")

def parse_quantity(measure_str):
    try:
        num = ''.join([c for c in measure_str if c.isdigit() or c == '.'])
        return float(num) if num else 1.0
    except:
        return 1.0
