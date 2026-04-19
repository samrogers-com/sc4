from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('ebay_manager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocialAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(choices=[('instagram', 'Instagram'), ('facebook', 'Facebook'), ('tiktok', 'TikTok'), ('youtube', 'YouTube'), ('reddit', 'Reddit'), ('pinterest', 'Pinterest')], max_length=20, unique=True)),
                ('handle', models.CharField(blank=True, max_length=100)),
                ('access_token', models.TextField(blank=True)),
                ('token_expiry', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='HashtagGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('category', models.CharField(help_text='e.g. starwars, startrek, marvel, general', max_length=50)),
                ('hashtags', models.TextField(help_text='Space-separated hashtags')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['category', 'name'],
            },
        ),
        migrations.CreateModel(
            name='PostDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('caption', models.TextField()),
                ('hashtags', models.TextField(blank=True, help_text='Space-separated hashtag list')),
                ('image_r2_key', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending Review'), ('approved', 'Approved'), ('scheduled', 'Scheduled'), ('published', 'Published'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('llm_model_used', models.CharField(blank=True, max_length=50)),
                ('generation_cost_usd', models.DecimalField(blank=True, decimal_places=6, max_digits=8, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, help_text="Sam's notes or edits")),
                ('listing', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='post_drafts', to='ebay_manager.ebaylisting')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PostSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_for', models.DateTimeField()),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('platform_post_id', models.CharField(blank=True, max_length=100)),
                ('error_message', models.TextField(blank=True)),
                ('account', models.ForeignKey(on_delete=models.deletion.CASCADE, to='social_manager.socialaccount')),
                ('draft', models.ForeignKey(on_delete=models.deletion.CASCADE, to='social_manager.postdraft')),
            ],
            options={
                'ordering': ['scheduled_for'],
            },
        ),
        migrations.AddField(
            model_name='postdraft',
            name='platforms',
            field=models.ManyToManyField(through='social_manager.PostSchedule', to='social_manager.socialaccount'),
        ),
        migrations.CreateModel(
            name='PlatformAnalytics',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('impressions', models.IntegerField(default=0)),
                ('likes', models.IntegerField(default=0)),
                ('comments', models.IntegerField(default=0)),
                ('link_clicks', models.IntegerField(default=0)),
                ('fetched_at', models.DateTimeField(auto_now=True)),
                ('schedule', models.OneToOneField(on_delete=models.deletion.CASCADE, to='social_manager.postschedule')),
            ],
        ),
    ]
