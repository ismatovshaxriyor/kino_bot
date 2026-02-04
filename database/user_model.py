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

    ai_usage = fields.IntField(default=0)
    ai_usage_date = fields.DateField(null=True)

    first_name = fields.CharField(max_length=128, null=True)
    last_name = fields.CharField(max_length=128, null=True)
    username = fields.CharField(max_length=128, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class UserMovieHistory(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='history')
    movie = fields.ForeignKeyField('models.Movie', related_name='viewed_by')
    viewed_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'movie')