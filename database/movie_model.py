from tortoise import models, fields


class Movie(models.Model):
    movie_id = fields.IntField(pk=True)
    movie_code = fields.IntField(unique=True)
