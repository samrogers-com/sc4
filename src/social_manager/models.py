from django.db import models


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('facebook', 'Facebook'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('reddit', 'Reddit'),
        ('pinterest', 'Pinterest'),
    ]
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, unique=True)
    handle = models.CharField(max_length=100, blank=True)
    access_token = models.TextField(blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.get_platform_display()} ({self.handle or "unlinked"})'


class PostDraft(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
    ]
    listing = models.ForeignKey(
        'ebay_manager.EbayListing',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='post_drafts',
    )
    caption = models.TextField()
    hashtags = models.TextField(blank=True, help_text='Space-separated hashtag list')
    image_r2_key = models.CharField(max_length=255, blank=True)
    platforms = models.ManyToManyField(SocialAccount, through='PostSchedule')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    llm_model_used = models.CharField(max_length=50, blank=True)
    generation_cost_usd = models.DecimalField(
        max_digits=8, decimal_places=6, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Sam's notes or edits")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        preview = self.caption[:40].replace('\n', ' ')
        return f'[{self.get_status_display()}] {preview}'

    def mark_manually_posted(self, platform: str) -> 'PostSchedule':
        """Record a manual (off-API) post on the given platform.

        Sets status to 'published' and writes a PostSchedule row with
        platform_post_id='manual' so later analytics can distinguish manual
        vs API-published posts. Safe to call once per platform; creates a
        SocialAccount placeholder if OAuth isn't connected yet.
        """
        from django.utils import timezone
        now = timezone.now()
        account, _ = SocialAccount.objects.get_or_create(platform=platform)
        sched = PostSchedule.objects.create(
            draft=self,
            account=account,
            scheduled_for=now,
            published_at=now,
            platform_post_id='manual',
        )
        if self.status != 'published':
            self.status = 'published'
            self.save(update_fields=['status'])
        return sched


class PostSchedule(models.Model):
    draft = models.ForeignKey(PostDraft, on_delete=models.CASCADE)
    account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE)
    scheduled_for = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    platform_post_id = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['scheduled_for']

    def __str__(self):
        return f'{self.account} @ {self.scheduled_for:%Y-%m-%d %H:%M}'


class PlatformAnalytics(models.Model):
    schedule = models.OneToOneField(PostSchedule, on_delete=models.CASCADE)
    impressions = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    link_clicks = models.IntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.schedule} — {self.impressions} impressions'


class HashtagGroup(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(
        max_length=50,
        help_text='e.g. starwars, startrek, marvel, general',
    )
    hashtags = models.TextField(help_text='Space-separated hashtags')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.name} ({self.category})'
