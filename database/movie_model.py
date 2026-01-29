from tortoise import models, fields
from tortoise.indexes import Index


class Movie(models.Model):
    movie_id = fields.IntField(pk=True)
    movie_code = fields.IntField(unique=True)
    file_id = fields.CharField(max_length=255, unique=True)
    movie_name = fields.CharField(max_length=255)
    movie_genre = fields.ForeignKeyField('models.Genre', related_name='movies')
    movie_country = fields.ForeignKeyField('models.Countries', related_name='movies')
    movie_year = fields.IntField()
    movie_duration = fields.IntField(null=True)
    movie_description = fields.TextField(null=True)
    total_rating_sum = fields.BigIntField(default=0)
    rating_count = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['movie_name']),
            Index(fields=['movie_year']),
            Index(fields=['movie_genre_id'])
        ]

    def __str__(self):
        return f"{self.movie_name} ({self.movie_year})"

    @property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.total_rating_sum / self.rating_count, 1)

    @property
    def duration_formatted(self) -> str:
        if not self.movie_duration:
            return "N/A"
        hours = self.movie_duration // 60
        minutes = self.movie_duration % 60
        return f"{hours}s {minutes}min" if hours else f"{minutes}min"
