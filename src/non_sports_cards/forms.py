# src/non_sports_cards/forms.py

from django import forms
from .models import NonSportsCards

class NonSportsCardsForm(forms.ModelForm):
    class Meta:
        model = NonSportsCards
        fields = ['title', 'manufacturer', 'date_manufactured']
        widgets = {
            'date_manufactured': forms.TextInput(attrs={'placeholder': 'YYYY', 'class': 'form-input'}),
        }

    # Example of a custom validation
    def clean_date_manufactured(self):
        date = self.cleaned_data.get('date_manufactured')
        if not date.isdigit() or len(date) != 4:
            raise forms.ValidationError('Please enter a valid 4-digit year.')
        return date
