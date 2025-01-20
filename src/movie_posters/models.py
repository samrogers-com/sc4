from django.db import models


class MoviePosters(models.Model):
    title = models.CharField(max_length=255)
    release_date = models.DateField(null=True, blank=True)  # Optional field for release date
    size = models.CharField(max_length=100, null=True, blank=True)  # Size of the poster
    description = models.TextField(null=True, blank=True)  # Description of the poster
    condition = models.CharField(max_length=100, null=True, blank=True)  # Condition of the poster

    def __str__(self):
        return f"{self.title} ({self.movie_title})"
