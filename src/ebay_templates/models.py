# file: src/ebay_templates/models.py

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from non_sports_cards.models import NonSportsCards
from comic_books.models import ComicBook  # Assuming ComicBook is an abstract base class
from movie_posters.models import MoviePosters


class SavedTemplate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_templates")
    name = models.CharField(max_length=255)
    content = models.TextField()  # Store template data as text (e.g., HTML)
    category = models.CharField(max_length=50, choices=[
        ('non_sports_cards', 'Non-Sports Cards'),
        ('comic_books', 'Comic Books'),
        ('movie_posters', 'Movie Posters'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.category})"


class GeneratedEbayTemplate(models.Model):
    TEMPLATE_TYPES = [
        ('non_sports_cards', 'Non-Sports Cards'),
        ('comic_books', 'Comic Books'),
        ('movie_posters', 'Movie Posters'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ebay_templates')
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    title = models.CharField(max_length=255)
    content_object_id = models.PositiveIntegerField()  # Generic relation to any model
    html_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    credits_used = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.get_template_type_display()} Template for {self.title} by {self.user.username}"

