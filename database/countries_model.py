from tortoise import models, fields


class Countries(models.Model):
    country_id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50, unique=True)