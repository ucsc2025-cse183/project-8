"""
This file defines the database models
"""

from pydal.validators import *

from .common import Field, db, auth

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
    Field("name", type="string", default=""),
    Field("type", type="string", default=""),
    Field("description", type="string", default="")
    Field("image", type="upload", uploadfolder=settings.UPLOADFOLDER),
    Field("author", type="string", default=""),
    Field("instruction_steps", type="string", default=""),
    Field("servings", type="integer")
)

# Link table
db.define_table(
    "link",
    Field("recipe_id", type="reference recipes"),
    Field("ingredient_id", type="reference ingredients"),
    Field("quantity_per_serving", type="integer")
)

# always commit models
db.commit()
