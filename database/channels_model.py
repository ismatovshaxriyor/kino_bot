from tortoise import fields, models


class Channels(models.Model):
    channel_id = fields.BigIntField(pk=True)
    name = fields.CharField(max_length=128)
    username = fields.CharField(max_length=50)

