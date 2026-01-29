from tortoise import models, fields


class Genre(models.Model):
    genre_id = fields.IntField(pk=True)
    name = fields.CharField(max_length=128, unique=True)