from tortoise import models, fields

class Rating(models.Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='ratings')
    movie = fields.ForeignKeyField('models.Movie', related_name='ratings')
    score = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'movie')
