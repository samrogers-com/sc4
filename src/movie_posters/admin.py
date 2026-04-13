from django.contrib import admin
from .models import MoviePosters, MoviePosterImage


@admin.register(MoviePosters)
class MoviePostersAdmin(admin.ModelAdmin):
    list_display = ('title', 'franchise', 'year', 'poster_type', 'condition', 'inventory_status', 'restoration_status', 'restoration_priority', 'restoration_type', 'validation_status', 'ebay_item_id')
    search_fields = ('title', 'franchise', 'artist', 'year')
    list_filter = ('inventory_status', 'restoration_status', 'restoration_priority', 'restoration_type', 'validation_status', 'franchise', 'poster_type', 'size', 'condition', 'linen_backed')


@admin.register(MoviePosterImage)
class MoviePosterImageAdmin(admin.ModelAdmin):
    list_display = ('poster', 'image_name', 'image_type', 'uploaded_by')
    search_fields = ('image_name', 'poster__title')
    list_filter = ('image_type',)
