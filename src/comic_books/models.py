# src/comic_books/models.py

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class Publisher(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    @staticmethod
    def get_unknown_publisher():
        # Get or create an "Unknown" publisher
        return Publisher.objects.get_or_create(name='Unknown')[0]

class ComicBook(models.Model):    
    title = models.CharField(max_length=200, default='Unknown')
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, default=Publisher.get_unknown_publisher)
    issue_number = models.IntegerField(default=1)
    release_date = models.DateField(null=True)

    class Meta:
        abstract = True
        unique_together = ('issue_number', 'publisher')  # Apply across all subclasses

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} ({self.publisher})"

class StarWarsMarvelComic(ComicBook):
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} (Star Wars Marvel)"

class StarWarsDarkHorseComic(ComicBook):
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} (Star Wars Dark Horse)"

class StarTrekDcComic(ComicBook):
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} (Star Trek DC)"

# Generalized Key Issue Facts model that can be related to any ComicBook
class KeyIssueFacts(models.Model):
    # Generic relation to any comic book model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    comic = GenericForeignKey('content_type', 'object_id')

    is_key_issue = models.BooleanField(default=False)

    # Store multiple key facts as a comma-separated string
    key_facts = models.TextField(blank=True, null=True, help_text="Provide details like first appearances, major events (comma-separated).")
    
    # Store characters as a comma-separated string
    characters_appearing = models.TextField(blank=True, help_text="List of important characters appearing (comma-separated).")
    
    # Store reasons as a comma-separated string
    key_reason = models.TextField(max_length=255, blank=True, help_text="Reason why this issue is a key issue (comma-separated).")

    # Helper method to split key_facts into a list
    def get_key_facts_list(self):
        return self.key_facts.split(',') if self.key_facts else []

    # Helper method to split characters_appearing into a list
    def get_characters_list(self):
        return self.characters_appearing.split(',') if self.characters_appearing else []

    # Helper method to split key_reason into a list
    def get_key_reasons_list(self):
        return self.key_reason.split(',') if self.key_reason else []

    def __str__(self):
        return f"Key Facts for {self.comic} #{self.object_id}"
