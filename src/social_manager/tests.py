from django.test import TestCase
from django.utils import timezone

from .models import (
    HashtagGroup,
    PlatformAnalytics,
    PostDraft,
    PostSchedule,
    SocialAccount,
)


class SocialAccountTests(TestCase):
    def test_str_with_handle(self):
        acct = SocialAccount.objects.create(platform='instagram', handle='@sams.collectibles')
        self.assertIn('Instagram', str(acct))
        self.assertIn('@sams.collectibles', str(acct))

    def test_str_without_handle(self):
        acct = SocialAccount.objects.create(platform='facebook')
        self.assertIn('unlinked', str(acct))


class PostDraftTests(TestCase):
    def test_default_status_pending(self):
        draft = PostDraft.objects.create(caption='hello world')
        self.assertEqual(draft.status, 'pending')

    def test_str_truncates_caption(self):
        long = 'x' * 100
        draft = PostDraft.objects.create(caption=long)
        s = str(draft)
        self.assertTrue(s.startswith('[Pending Review]'))
        self.assertLessEqual(len(s.split('] ', 1)[1]), 40)


class PostScheduleTests(TestCase):
    def test_ordering_by_scheduled_for(self):
        draft = PostDraft.objects.create(caption='c')
        a1 = SocialAccount.objects.create(platform='instagram')
        a2 = SocialAccount.objects.create(platform='facebook')
        later = timezone.now() + timezone.timedelta(hours=2)
        earlier = timezone.now() + timezone.timedelta(hours=1)
        PostSchedule.objects.create(draft=draft, account=a1, scheduled_for=later)
        PostSchedule.objects.create(draft=draft, account=a2, scheduled_for=earlier)
        all_scheds = list(PostSchedule.objects.all())
        self.assertLess(all_scheds[0].scheduled_for, all_scheds[1].scheduled_for)


class PlatformAnalyticsTests(TestCase):
    def test_onetoone_with_schedule(self):
        draft = PostDraft.objects.create(caption='c')
        acct = SocialAccount.objects.create(platform='instagram')
        sched = PostSchedule.objects.create(
            draft=draft, account=acct, scheduled_for=timezone.now()
        )
        PlatformAnalytics.objects.create(schedule=sched, impressions=100, likes=5)
        self.assertEqual(sched.platformanalytics.impressions, 100)


class HashtagGroupTests(TestCase):
    def test_str_includes_category(self):
        g = HashtagGroup.objects.create(
            name='Star Wars keys',
            category='starwars',
            hashtags='#starwarscards #nonsportcards #vintagecards',
        )
        self.assertIn('starwars', str(g))


class CaptionGeneratorTests(TestCase):
    def test_placeholder_raises_not_implemented(self):
        from social_manager.services.caption_generator import generate_caption
        with self.assertRaises(NotImplementedError):
            generate_caption(listing=None, platform='instagram')
