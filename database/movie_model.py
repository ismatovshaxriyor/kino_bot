from enum import Enum
from tortoise import models, fields
from tortoise.indexes import Index

class QualityEnum(str, Enum):
    P1080 = '1080p'
    P720 = '720p'
    P480 = '480p'
    P360 = '360p'

class LanguageEnum(str, Enum):
    UZBEK = "O'zbek tilida"
    ENGLISH = "Ingliz tilida"
    RUSSIAN = "Rus tilida"

class Movie(models.Model):
    movie_id = fields.IntField(pk=True)
    movie_code = fields.IntField(unique=True)
    file_id = fields.TextField()
    movie_name = fields.CharField(max_length=255)
    movie_genre = fields.ManyToManyField('models.Genre', related_name='movies', null=True)
    movie_country = fields.ManyToManyField('models.Countries', related_name='movies', null=True)
    movie_year = fields.IntField(null=True)
    movie_duration = fields.IntField(null=True)
    movie_description = fields.TextField(null=True)
    movie_quality = fields.CharEnumField(QualityEnum, null=True)
    movie_language = fields.CharEnumField(LanguageEnum, null=True)
    total_rating_sum = fields.BigIntField(default=0)
    rating_count = fields.IntField(default=0)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['movie_name']),
            Index(fields=['movie_year'])
        ]

    def __str__(self):
        return f"{self.movie_name} ({self.movie_year})"

    @property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        return round(self.total_rating_sum / self.rating_count, 2)

    @property
    def duration_formatted(self) -> str:
        if not self.movie_duration:
            return "N/A"
        hours = self.movie_duration // 60
        minutes = self.movie_duration % 60
        return f"{hours}s {minutes}min" if hours else f"{minutes}min"


class MoviePart(models.Model):
    part_id = fields.IntField(pk=True)
    movie = fields.ForeignKeyField('models.Movie', related_name='parts', on_delete=fields.CASCADE)
    part_number = fields.IntField()
    title = fields.CharField(max_length=255, null=True)
    file_id = fields.TextField()

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        unique_together = (("movie", "part_number"),)
        ordering = ["part_number"]

    def __str__(self):
        return f"{self.movie.movie_name} - {self.part_number}-qism"
