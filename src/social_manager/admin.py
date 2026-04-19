from django.contrib import admin

from .models import (
    HashtagGroup,
    PlatformAnalytics,
    PostDraft,
    PostSchedule,
    SocialAccount,
)


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('platform', 'handle', 'is_active', 'token_expiry', 'updated_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('handle',)
    readonly_fields = ('created_at', 'updated_at')


class PostScheduleInline(admin.TabularInline):
    model = PostSchedule
    extra = 0
    autocomplete_fields = ('account',)


@admin.register(PostDraft)
class PostDraftAdmin(admin.ModelAdmin):
    list_display = ('status', 'short_caption', 'listing', 'llm_model_used', 'created_at')
    list_filter = ('status', 'llm_model_used', 'created_at')
    search_fields = ('caption', 'hashtags', 'notes')
    autocomplete_fields = ('listing',)
    readonly_fields = ('created_at',)
    inlines = [PostScheduleInline]
    actions = ['mark_approved', 'mark_rejected']

    @admin.display(description='Caption')
    def short_caption(self, obj):
        return (obj.caption or '')[:60]

    @admin.action(description='Mark selected drafts as approved')
    def mark_approved(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='approved', approved_at=timezone.now())

    @admin.action(description='Mark selected drafts as rejected')
    def mark_rejected(self, request, queryset):
        queryset.update(status='rejected')


@admin.register(PostSchedule)
class PostScheduleAdmin(admin.ModelAdmin):
    list_display = ('draft', 'account', 'scheduled_for', 'published_at')
    list_filter = ('account__platform',)
    autocomplete_fields = ('draft', 'account')


@admin.register(PlatformAnalytics)
class PlatformAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        'schedule', 'impressions', 'likes', 'comments', 'link_clicks', 'fetched_at'
    )
    readonly_fields = ('fetched_at',)


@admin.register(HashtagGroup)
class HashtagGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'created_at')
    list_filter = ('category',)
    search_fields = ('name', 'hashtags')
