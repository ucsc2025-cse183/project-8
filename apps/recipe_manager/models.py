"""
This file defines the database models
"""

from pydal.validators import *
from datetime import datetime

from .common import Field, db, auth
from . import settings

### Define your table below
#
# db.define_table('thing', Field('name'))
#
## always commit your models to avoid problems later
#
# db.commit()
#

# Ingredient table
db.define_table(
    "ingredients",
    Field("name", type="string", default=""),
    Field("unit", type="string"),
    Field("calories_per_unit", type="integer"),
    Field("description", type="string")
)

# Recipe table
db.define_table(
    "recipes",
    Field("name", type="string", required=True),
    Field("type", type="string", default=""),
    Field("image", "upload", uploadfolder=settings.UPLOAD_FOLDER),
    Field("servings", type="integer", default=1),
    Field("description", type="text"),
    Field("instructions", type="text"),
    Field("author", "reference auth_user"),
    Field("created_on", type="datetime", default=datetime.utcnow),
    Field("updated_on", type="datetime", update=datetime.utcnow)
    
)

# Recipe-Ingredient link table
db.define_table(
    "recipe_ingredients",
    Field("recipe_id", "reference recipes"),
    Field("ingredient_id", "reference ingredients"),
    Field("quantity", type="double", required=True)
)

# always commit models
db.commit()

from .private.populate_recipes import import_recipes
import_recipes(db)