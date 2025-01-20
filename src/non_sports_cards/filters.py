# src/non_sports_cards/filters.py

import django_filters
from django import forms
from .models import NonSportsCards

class NonSportsCardsFilter(django_filters.FilterSet):
    # Access MANUFACTURERS directly from the NonSportsCards class
    manufacturer = django_filters.ChoiceFilter(
        choices=NonSportsCards.MANUFACTURERS,  # Access MANUFACTURERS inside the class
        empty_label='All Manufacturers',
        widget=forms.Select(attrs={
            'class': 'form-select bg-gray-100 border border-gray-300 rounded-md shadow-sm'
        }),
        label='Select Manufacturer'
    )

    title = django_filters.CharFilter(
        field_name='title',
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-input bg-gray-100 border border-gray-300 rounded-md shadow-sm', 
            'placeholder': 'Enter Title'
        }),
        label='Search by Title'
    )

    date_manufactured = django_filters.CharFilter(
        field_name='date_manufactured',
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={
            'class': 'form-input bg-gray-100 border border-gray-300 rounded-md shadow-sm', 
            'placeholder': 'Enter Year (YYYY)'
        }),
        label='Manufacture Year'
    )

    class Meta:
        model = NonSportsCards
        fields = ['title', 'manufacturer', 'date_manufactured']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print(f"Filter initialized with data: {self.data}")
