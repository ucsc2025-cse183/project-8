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


# define post_item table
db.define_table(
    "post_item",
    Field("content", "text", requires=IS_NOT_EMPTY()),
    auth.signature
)

# define tag_item table
db.define_table(
    "tag_item",
    Field("name", "string"),
    Field("post_item_id", "reference post_item"),
    auth.signature
)

# always commit models
db.commit()
