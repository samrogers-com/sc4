# src/non_sports_cards/models.py

# file: src/non_sports_cards/models.py

from django.db import models
from django.core.exceptions import ValidationError
from utils.s3_url_builder import construct_image_url

def validate_key_features(value):
    if not isinstance(value, list):
        raise ValidationError("Key features must be a list.")
    for feature in value:
        if not isinstance(feature, str):
            raise ValidationError("Each feature in key features must be a string.")

class NonSportsCards(models.Model):
    MANUFACTURERS = [
        ('Topps', 'Topps'),
        ('Fleer', 'Fleer'),
        ('SkyBox', 'SkyBox'),
        ('Donruss', 'Donruss (Pinnacle Brands)'),
        ('Inkworks', 'Inkworks'),
        ('Rittenhouse Archives', 'Rittenhouse Archives'),
        ('Leaf', 'Leaf'),
        ('Dart Flipcards', 'Dart Flipcards'),
        ('Pacific', 'Pacific'),
        ('Artbox', 'Artbox'),
        ('Cryptozoic', 'Cryptozoic Entertainment'),
        ('Upper Deck', 'Upper Deck'),
        ('Breygent', 'Breygent Marketing'),
        ('Comic Images', 'Comic Images'),
        ('Impel Marketing', 'Impel Marketing'),
        ('Panini', 'Panini'),
        ('Krome', 'Krome Productions'),
        ('Philadelphia Gum', 'Philadelphia Gum Company'),
        ('Brooke Bond', 'Brooke Bond'),
        ('FPG', 'FPG (Friedlander Publishing Group)'),
        ('Marvel Comics', 'Marvel Comics'),
        ('Wizards of the Coast', 'Wizards of the Coast'),
    ]

    category = models.CharField(max_length=100, default="Uncategorized")
    title = models.CharField(max_length=255, unique=True)
    manufacturer = models.CharField(max_length=255, choices=MANUFACTURERS, default='Unknown')
    date_manufactured = models.CharField(max_length=4, null=True, blank=True)
    number_of_packs_per_box = models.IntegerField(null=True, blank=True)
    number_of_cards_per_pack = models.IntegerField(null=True, blank=True)
    number_of_sets_per_box = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    number_of_cards_in_a_set = models.IntegerField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    key_features = models.JSONField(default=list, validators=[validate_key_features], null=True, blank=True)
    app = models.CharField(max_length=50, default="ns-cards")
    image_type = models.CharField(max_length=50, default="sets")
    sub_category = models.CharField(max_length=100)

    class Meta:
        db_table = 'nonsportscards'

    def __str__(self):
        return self.title or "Unknown Title"

    def save(self, *args, **kwargs):
        if isinstance(self.key_features, str):
            self.key_features = [self.key_features]  # Convert single string to list
        super().save(*args, **kwargs)

    @property
    def base_url(self):
        """
        Dynamically construct the base URL for this card's images.
        """
        return construct_image_url(
            app=self.app,
            image_type=self.image_type,
            category=self.category,
            sub_category=self.sub_category,
            image_name=""
        )

    @property
    def full_image_url(self):
        """
        Get the full image URL for a specific image name.
        """
        if not self.image_name:
            return None
        return construct_image_url(
            app=self.app,
            image_type=self.image_type,
            category=self.category,
            sub_category=self.sub_category,
            image_name=self.image_name
        )

class NonSportsCardImage(models.Model):
    """
    Represents individual images associated with NonSportsCards.
    Each image is stored with a reference to its S3 path.
    """
    non_sports_card = models.ForeignKey(
        NonSportsCards,
        on_delete=models.CASCADE,
        related_name="images"
    )
    image_name = models.CharField(max_length=255)  # Example: marvel_universe_92_box_frt-1.jpg
    image_type = models.CharField(
        max_length=50,
        choices=[
            ('front', 'Front'),
            ('back', 'Back'),
            ('other', 'Other'),
        ],
        default='other'
    )
    s3_path = models.URLField(help_text="Full S3 path to the image")

    class Meta:
        db_table = 'nonsportscardimage'

    def __str__(self):
        return f"{self.non_sports_card.title} - {self.image_name} ({self.image_type})"

    @property
    def full_image_url(self):
        """
        Returns the full S3 path to the image.
        """
        return self.s3_path
    @property
    def full_image_url(self):
        """
        Returns the full S3 path to the image.
        """
        return self.s3_path

# Model for Non-Sports Chase Cards
class NonSportsChaseCards(models.Model):
    CHASE_TYPES = [
        ('Holographic', 'Holographic Cards'),
        ('Foil', 'Foil Cards'),
        ('Embossed', 'Embossed Cards'),
        ('Die-Cut', 'Die-Cut Cards'),
        ('Parallel', 'Parallel Cards')
    ]

    nonsportscard = models.ForeignKey(NonSportsCards, on_delete=models.CASCADE, related_name='nonsports_chase_cards', null=True, blank=True)
    card_number = models.CharField(max_length=10, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    chase_type = models.CharField(max_length=50, choices=CHASE_TYPES, null=True, blank=True)

    class Meta:
        db_table = 'nonsports_chase_cards'

    def __str__(self):
        return f"{self.chase_type}: {self.title} ({self.card_number})"


# Model for Non-Sports Insert Cards
class NonSportsInsertCards(models.Model):
    INSERT_TYPES = [
        ('Autographed', 'Autographed Cards'),
        ('Sketch', 'Sketch Cards'),
        ('Relic', 'Relic/Memorabilia Cards'),
        ('Lenticular', 'Lenticular/3D Cards'),
        ('Puzzle', 'Puzzle Cards'),
        ('Costume', 'Costume Cards')
    ]

    nonsportscard = models.ForeignKey(NonSportsCards, on_delete=models.CASCADE, related_name='nonsports_insert_cards', null=True, blank=True)
    card_number = models.CharField(max_length=10, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    insert_type = models.CharField(max_length=50, choices=INSERT_TYPES, null=True, blank=True)

    class Meta:
        db_table = 'nonsports_insert_cards'

    def __str__(self):
        return f"{self.insert_type}: {self.title} ({self.card_number})"


# Model for Non-Sports Special Cards
class NonSportsSpecialCards(models.Model):
    SPECIAL_TYPES = [
        ('Promo', 'Promo Cards'),
        ('LimitedEdition', 'Limited Edition Cards'),
        ('Redemption', 'Redemption Cards')
    ]

    nonsportscard = models.ForeignKey(NonSportsCards, on_delete=models.CASCADE, related_name='nonsports_special_cards', null=True, blank=True)
    card_number = models.CharField(max_length=10, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    special_type = models.CharField(max_length=50, choices=SPECIAL_TYPES, null=True, blank=True)
    limited_edition_number = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        db_table = 'nonsports_special_cards'

    def __str__(self):
        return f"{self.special_type}: {self.title} ({self.card_number})"


# Model for Boxes, which extends NonSportsCards
class NonSportsCardsBoxes(NonSportsCards):
    class Meta:
        db_table = 'nonsportscards_boxes'


# Model for Base Sets, which extends NonSportsCards
class NonSportsCardsBaseSets(NonSportsCards):
    class Meta:
        db_table = 'nonsportscards_base_sets'


# Model for Special Sets, which extends NonSportsCards
class NonSportsCardsSpecialSets(NonSportsCards):
    class Meta:
        db_table = 'nonsportscards_special_sets'


# Model for Singles, which references base set and special cards (chase, insert, special)
class NonSportsCardsSingles(models.Model):
    base_set = models.ForeignKey(NonSportsCardsBaseSets, on_delete=models.CASCADE, null=True, blank=True, related_name='singles')
    chase_card = models.ForeignKey('NonSportsChaseCards', on_delete=models.CASCADE, null=True, blank=True, related_name='singles')
    insert_card = models.ForeignKey('NonSportsInsertCards', on_delete=models.CASCADE, null=True, blank=True, related_name='singles')
    special_card = models.ForeignKey('NonSportsSpecialCards', on_delete=models.CASCADE, null=True, blank=True, related_name='singles')

    def __str__(self):
        if self.base_set:
            return f"Single from Base Set: {self.base_set.title}"
        if self.chase_card:
            return f"Single Chase Card: {self.chase_card.title}"
        if self.insert_card:
            return f"Single Insert Card: {self.insert_card.title}"
        if self.special_card:
            return f"Single Special Card: {self.special_card.title}"

    class Meta:
        db_table = 'nonsportscards_singles'

