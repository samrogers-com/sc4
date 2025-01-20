# src/non_sports_cards/admin.py

from django.contrib import admin
from .models import (
    NonSportsCards, NonSportsChaseCards, NonSportsInsertCards, 
    NonSportsSpecialCards, NonSportsCardsBoxes, NonSportsCardsBaseSets, 
    NonSportsCardsSpecialSets, NonSportsCardsSingles
)

@admin.register(NonSportsCards)
class NonSportsCardsAdmin(admin.ModelAdmin):
    list_display = ('title', 'manufacturer', 'date_manufactured', 'number_of_packs_per_box', 'number_of_cards_per_pack', 'number_of_cards_in_a_set', 'number_of_sets_per_box', 'number_of_cards_in_a_set', 'description')
    search_fields = ('title', 'manufacturer', 'date_manufactured')
    list_filter = ('title', 'manufacturer', 'date_manufactured')

@admin.register(NonSportsChaseCards)
class NonSportsChaseCardsAdmin(admin.ModelAdmin):
    list_display = ('title', 'card_number', 'chase_type', 'nonsportscard')
    search_fields = ('title', 'card_number')
    list_filter = ('title', 'chase_type',)

@admin.register(NonSportsInsertCards)
class NonSportsInsertCardsAdmin(admin.ModelAdmin):
    list_display = ('title', 'card_number', 'insert_type', 'nonsportscard')
    search_fields = ('title', 'card_number')
    list_filter = ('title', 'insert_type',)

@admin.register(NonSportsSpecialCards)
class NonSportsSpecialCardsAdmin(admin.ModelAdmin):
    list_display = ('title', 'card_number', 'special_type', 'limited_edition_number', 'nonsportscard')
    search_fields = ('title', 'card_number', 'limited_edition_number')
    list_filter = ('special_type',)

@admin.register(NonSportsCardsBoxes)
class NonSportsCardsBoxesAdmin(admin.ModelAdmin):
    list_display = ('title', 'manufacturer', 'date_manufactured')
    search_fields = ('title', 'manufacturer', 'date_manufactured')
    list_filter = ('title', 'manufacturer', 'date_manufactured')

@admin.register(NonSportsCardsBaseSets)
class NonSportsCardsBaseSetsAdmin(admin.ModelAdmin):
    list_display = ('title', 'manufacturer', 'date_manufactured')
    search_fields = ('title', 'manufacturer', 'date_manufactured')
    list_filter = ('title', 'manufacturer', 'date_manufactured')

@admin.register(NonSportsCardsSpecialSets)
class NonSportsCardsSpecialSetsAdmin(admin.ModelAdmin):
    list_display = ('title', 'manufacturer', 'date_manufactured')
    search_fields = ('title', 'manufacturer', 'date_manufactured')
    list_filter = ('title', 'manufacturer', 'date_manufactured')

@admin.register(NonSportsCardsSingles)
class NonSportsCardsSinglesAdmin(admin.ModelAdmin):
    list_display = ('base_set', 'chase_card', 'insert_card', 'special_card')
    search_fields = ('base_set__title', 'chase_card__title', 'insert_card__title', 'special_card__title')
    list_filter = ('base_set', 'chase_card', 'insert_card', 'special_card')

