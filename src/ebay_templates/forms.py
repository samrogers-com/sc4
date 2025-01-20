# file: src/ebay_templates/forms.py

from django import forms
from non_sports_cards.models import NonSportsCardImage, NonSportsCards
from comic_books.models import (
    StarWarsMarvelComic, 
    StarWarsDarkHorseComic, 
    StarTrekDcComic
)
from movie_posters.models import MoviePosters

class NonSportsCardImageForm(forms.ModelForm):
    class Meta:
        model = NonSportsCardImage
        fields = ['image_name', 'image_type', 's3_path']
class NonSportsCardForm(forms.ModelForm):
    class Meta:
        model = NonSportsCards
        fields = [
            'title', 
            'manufacturer', 
            'date_manufactured', 
            'number_of_packs_per_box',
            'number_of_cards_per_pack', 
            'number_of_sets_per_box', 
            'number_of_cards_in_a_set',
            'description', 
            'key_features'
        ]


# Abstract base form for ComicBook models
class BaseComicBookForm(forms.ModelForm):
    class Meta:
        fields = [
            'title', 
            'publisher', 
            'issue_number', 
            'release_date', 
            'description'
        ]

# Generic ComicBookForm for use in views requiring a single reference
ComicBookForm = BaseComicBookForm

# Concrete forms inheriting from BaseComicBookForm
class StarWarsMarvelComicForm(BaseComicBookForm):
    class Meta(BaseComicBookForm.Meta):
        model = StarWarsMarvelComic


class StarWarsDarkHorseComicForm(BaseComicBookForm):
    class Meta(BaseComicBookForm.Meta):
        model = StarWarsDarkHorseComic


class StarTrekDcComicForm(BaseComicBookForm):
    class Meta(BaseComicBookForm.Meta):
        model = StarTrekDcComic


class MoviePostersForm(forms.ModelForm):
    class Meta:
        model = MoviePosters
        fields = [
            'title', 
            'release_date', 
            'size', 
            'description', 
            'condition'
        ]

