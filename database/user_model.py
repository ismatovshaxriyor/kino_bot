from tortoise.models import Model
from tortoise import fields
from enum import Enum

class USER_TYPE(str, Enum):
    ADMIN = 'admin'
    USER = 'user'


class User(Model):
    id = fields.IntField(pk=True)
    telegram_id = fields.BigIntField(unique=True)
    user_type = fields.CharEnumField(USER_TYPE, default=USER_TYPE.USER)

    first_name = fields.CharField(max_length=128, null=True)
    last_name = fields.CharField(max_length=128, null=True)
    username = fields.CharField(max_length=128, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class UserMovieHistory(Model):
    user = fields.ForeignKeyField('models.User', related_name='user')
    movie = fields.ForeignKeyField('models.Movie', related_name='movie')

    class Meta:
        unique_together = ('user', 'movie')