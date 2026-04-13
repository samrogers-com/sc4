from django.db import models
from django.contrib.auth.models import User


class MoviePosters(models.Model):
    VALIDATION_STATUSES = [
        ('unvalidated', 'Unvalidated'),
        ('enriched', 'Enriched'),
        ('verified', 'Verified'),
    ]

    POSTER_SIZES = [
        ('one_sheet', 'One Sheet (27x41)'),
        ('half_sheet', 'Half Sheet (22x28)'),
        ('insert', 'Insert (14x36)'),
        ('lobby_card', 'Lobby Card (11x14)'),
        ('mini', 'Mini (varies)'),
        ('three_sheet', 'Three Sheet (41x81)'),
        ('six_sheet', 'Six Sheet (81x81)'),
        ('24x36', 'Standard (24x36)'),
        ('bus_stop', 'Bus Stop/Subway (varies)'),
        ('other', 'Other'),
    ]

    POSTER_TYPES = [
        ('original', 'Original Theatrical Release'),
        ('reissue', 'Re-issue/Re-release'),
        ('reproduction', 'Reproduction/Reprint'),
        ('advance', 'Advance/Teaser'),
        ('special', 'Special Edition'),
        ('international', 'International'),
        ('commercial', 'Commercial Print'),
        ('promo', 'Promotional'),
    ]

    CONDITIONS = [
        ('mint', 'Mint'),
        ('near_mint', 'Near Mint'),
        ('very_fine', 'Very Fine'),
        ('fine', 'Fine'),
        ('very_good', 'Very Good'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]

    # Core fields
    title = models.CharField(max_length=255)
    year = models.CharField(max_length=4, null=True, blank=True)
    franchise = models.CharField(max_length=100, null=True, blank=True)
    artist = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    # Poster specifics
    poster_type = models.CharField(max_length=50, choices=POSTER_TYPES, null=True, blank=True)
    size = models.CharField(max_length=50, choices=POSTER_SIZES, null=True, blank=True)
    dimensions = models.CharField(max_length=50, null=True, blank=True)
    country_of_origin = models.CharField(max_length=100, null=True, blank=True)
    condition = models.CharField(max_length=50, choices=CONDITIONS, null=True, blank=True)
    linen_backed = models.BooleanField(default=False)
    rolled_or_folded = models.CharField(
        max_length=10,
        choices=[('rolled', 'Rolled'), ('folded', 'Folded')],
        null=True,
        blank=True,
    )

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

    # Restoration tracking
    RESTORATION_STATUSES = [
        ('none', 'No Treatment Needed'),
        ('recommended', 'Recommended'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]
    RESTORATION_TYPES = [
        ('linen_backing', 'Linen-Backing'),
        ('tear_repair', 'Tear Repair'),
        ('color_touch', 'Color Touch-Up'),
        ('cleaning', 'Cleaning'),
        ('deacidification', 'Deacidification'),
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
        db_table = 'movie_posters'

    def __str__(self):
        return self.title or "Unknown Poster"


class MoviePosterImage(models.Model):
    poster = models.ForeignKey(MoviePosters, on_delete=models.CASCADE, related_name='images')
    image_name = models.CharField(max_length=255)
    image_type = models.CharField(max_length=50, choices=[
        ('front', 'Front'),
        ('back', 'Back'),
        ('detail', 'Detail/Close-up'),
        ('other', 'Other'),
    ])
    s3_path = models.URLField()
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_poster_images')

    class Meta:
        db_table = 'movie_poster_images'

    def __str__(self):
        return f"{self.poster.title} - {self.image_name} ({self.image_type})"
