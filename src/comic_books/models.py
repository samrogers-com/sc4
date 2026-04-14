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
    VALIDATION_STATUSES = [
        ('unvalidated', 'Unvalidated'),
        ('enriched', 'Enriched'),
        ('verified', 'Verified'),
    ]

    CONDITIONS = [
        ('near_mint_mint', 'NM/M (9.2+)'),
        ('near_mint', 'NM (9.0-9.2)'),
        ('very_fine_near_mint', 'VF/NM (8.0-9.0)'),
        ('very_fine', 'VF (7.0-8.0)'),
        ('fine_very_fine', 'F/VF (6.0-7.0)'),
        ('fine', 'Fine (5.0-6.0)'),
        ('very_good_fine', 'VG/F (4.0-5.0)'),
        ('very_good', 'VG (3.0-4.0)'),
        ('good', 'Good (1.8-3.0)'),
        ('fair', 'Fair (1.0-1.8)'),
        ('poor', 'Poor (0.5-1.0)'),
    ]

    title = models.CharField(max_length=200, default='Unknown')
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, default=Publisher.get_unknown_publisher)
    issue_number = models.IntegerField(default=1)
    release_date = models.DateField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    condition = models.CharField(max_length=50, choices=CONDITIONS, null=True, blank=True)

    # eBay integration
    ebay_listing_url = models.URLField(null=True, blank=True)
    ebay_item_id = models.CharField(max_length=20, null=True, blank=True)

    # Tracking
    validation_status = models.CharField(max_length=20, choices=VALIDATION_STATUSES, default='unvalidated')

    # Inventory status
    INVENTORY_STATUSES = [
        ('in_stock', 'In Stock'),
        ('sold_out', 'Sold Out'),
        ('reserved', 'Reserved'),
        ('listed', 'Listed on eBay'),
    ]
    inventory_status = models.CharField(max_length=20, choices=INVENTORY_STATUSES, default='in_stock')

    # Weight for shipping
    weight_lbs = models.IntegerField(default=0, help_text='Weight - pounds')
    weight_oz = models.IntegerField(default=0, help_text='Weight - ounces')

    # Restoration tracking
    RESTORATION_STATUSES = [
        ('none', 'No Treatment Needed'),
        ('recommended', 'Recommended'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    RESTORATION_TYPES = [
        ('cleaning', 'Cleaning'),
        ('pressing', 'Pressing'),
        ('pressing_cleaning', 'Pressing + Cleaning'),
        ('whitening', 'Page Whitening'),
        ('tear_repair', 'Tear Repair'),
        ('color_touch', 'Color Touch-Up'),
        ('cgc_submission', 'CGC/CBCS Submission'),
    ]
    RESTORATION_PRIORITIES = [
        (1, '1 - Critical (High Value)'),
        (2, '2 - High'),
        (3, '3 - Medium'),
        (4, '4 - Low'),
        (5, '5 - Skip'),
    ]
    restoration_status = models.CharField(max_length=20, choices=RESTORATION_STATUSES, default='none')
    restoration_type = models.CharField(max_length=30, choices=RESTORATION_TYPES, null=True, blank=True)
    restoration_priority = models.IntegerField(choices=RESTORATION_PRIORITIES, null=True, blank=True)
    restoration_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    pre_restoration_grade = models.CharField(max_length=20, null=True, blank=True)
    post_restoration_grade = models.CharField(max_length=20, null=True, blank=True)
    pre_restoration_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    post_restoration_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    restoration_notes = models.TextField(null=True, blank=True)
    restoration_completed_date = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True
        unique_together = ('issue_number', 'publisher')

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} ({self.publisher})"


class StarWarsMarvelComic(ComicBook):

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} (Star Wars Marvel)"


class StarWarsDarkHorseComic(ComicBook):

    def __str__(self):
        return f"{self.title} #{self.issue_number:03d} (Star Wars Dark Horse)"


class StarTrekDcComic(ComicBook):

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
