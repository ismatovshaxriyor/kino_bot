from tortoise.models import Model
from tortoise import fields


class User(Model):
    first_name = fields.CharField(max_length=128)
    last_name = fields.CharField(max_length=128, null=True)
    username = fields.CharField(max_length=128, null=True)

    
    created_at = fields.DatetimeField(auto_add_now=True)