# src/comic_books/admin.py

from django.contrib import admin
from .models import Publisher, StarWarsMarvelComic, StarWarsDarkHorseComic, StarTrekDcComic, KeyIssueFacts

@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

# Register StarWarsMarvelComic in the admin for easier management
@admin.register(StarWarsMarvelComic)
class StarWarsMarvelComicAdmin(admin.ModelAdmin):
    list_display = ('title', 'issue_number', 'release_date')
    search_fields = ('title', 'issue_number')
    list_filter = ('release_date',)

@admin.register(StarWarsDarkHorseComic)
class StarWarsDarkHorseComicAdmin(admin.ModelAdmin):
    list_display = ('title', 'issue_number', 'release_date')
    search_fields = ('title', 'issue_number')
    list_filter = ('release_date',)

@admin.register(StarTrekDcComic)
class StarTrekDcComicAdmin(admin.ModelAdmin):
    list_display = ('title', 'issue_number', 'release_date')
    search_fields = ('title', 'issue_number')
    list_filter = ('release_date',)

@admin.register(KeyIssueFacts)
class KeyIssueFactsAdmin(admin.ModelAdmin):
    list_display = ('comic', 'is_key_issue', 'key_reason')
    search_fields = ('comic__title', 'key_reason')
    
    # Remove 'is_first_appearance' from the list filter, as it's no longer a field
    list_filter = ('is_key_issue',)

    def get_key_reasons(self, obj):
        return ', '.join(obj.get_key_reasons_list())

    def get_key_facts(self, obj):
        return ', '.join(obj.get_key_facts_list())

    def get_characters(self, obj):
        return ', '.join(obj.get_characters_list())
    
    get_key_reasons.short_description = 'Key Reasons'
    get_key_facts.short_description = 'Key Facts'
    get_characters.short_description = 'Characters Appearing'
