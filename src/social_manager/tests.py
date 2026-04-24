from django.test import TestCase
from django.urls import reverse
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


class MarkManuallyPostedTests(TestCase):
    def test_marks_published_and_creates_schedule(self):
        draft = PostDraft.objects.create(caption='c', status='approved')
        sched = draft.mark_manually_posted('instagram')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'published')
        self.assertEqual(sched.platform_post_id, 'manual')
        self.assertIsNotNone(sched.published_at)
        self.assertEqual(sched.account.platform, 'instagram')

    def test_creates_placeholder_account_when_missing(self):
        self.assertFalse(SocialAccount.objects.filter(platform='tiktok').exists())
        draft = PostDraft.objects.create(caption='c')
        draft.mark_manually_posted('tiktok')
        self.assertTrue(SocialAccount.objects.filter(platform='tiktok').exists())

    def test_reuses_existing_account(self):
        acct = SocialAccount.objects.create(platform='facebook', handle='@sc')
        draft = PostDraft.objects.create(caption='c')
        sched = draft.mark_manually_posted('facebook')
        self.assertEqual(sched.account_id, acct.id)
        self.assertEqual(SocialAccount.objects.filter(platform='facebook').count(), 1)

    def test_multiple_platforms_create_separate_schedules(self):
        draft = PostDraft.objects.create(caption='c', status='approved')
        draft.mark_manually_posted('instagram')
        draft.mark_manually_posted('facebook')
        self.assertEqual(PostSchedule.objects.filter(draft=draft).count(), 2)


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
    """Tests use an injected fake client — no real Anthropic API calls."""

    def _fake_client(self, response_text: str, input_tokens: int = 200, output_tokens: int = 80):
        class _Usage:
            pass

        class _TextBlock:
            pass

        class _Response:
            pass

        class _Messages:
            def create(self_, **kwargs):
                resp = _Response()
                block = _TextBlock()
                block.text = response_text
                resp.content = [block]
                usage = _Usage()
                usage.input_tokens = input_tokens
                usage.output_tokens = output_tokens
                resp.usage = usage
                return resp

        class _Client:
            messages = _Messages()

        return _Client()

    def _fake_listing(self):
        from ebay_manager.models import EbayListing
        return EbayListing.objects.create(
            title='1988 Topps Howard the Duck Wax Box — Factory Sealed',
            price='149.95',
            sku='1988-TOPPS-HOWARD-THE-DUCK-BOX',
            ebay_item_id='327106630765',
            category_id='261035',
            status='active',
        )

    def test_generates_caption_and_hashtags(self):
        from social_manager.services.caption_generator import generate_caption
        listing = self._fake_listing()
        body = (
            '{"caption": "Cult-classic 1988 Howard the Duck sealed box — 36 packs.",'
            ' "hashtags": ["#HowardTheDuck", "#Topps", "#NonSportCards", "#Vintage1988", "#TradingCards"]}'
        )
        result = generate_caption(listing, platform='instagram', client=self._fake_client(body))
        self.assertIn('Howard the Duck', result['caption'])
        self.assertEqual(len(result['hashtags']), 5)
        self.assertTrue(all(h.startswith('#') for h in result['hashtags']))
        self.assertGreater(result['cost_usd'], 0)

    def test_normalizes_hashtags_without_hash_prefix(self):
        from social_manager.services.caption_generator import generate_caption
        listing = self._fake_listing()
        body = '{"caption": "x", "hashtags": ["topps", "#already", "  spaced  "]}'
        result = generate_caption(listing, platform='instagram', client=self._fake_client(body))
        self.assertEqual(result['hashtags'], ['#topps', '#already', '#spaced'])

    def test_rejects_non_json_response(self):
        from social_manager.services.caption_generator import (
            CaptionGenerationError, generate_caption,
        )
        listing = self._fake_listing()
        with self.assertRaises(CaptionGenerationError):
            generate_caption(
                listing, platform='instagram',
                client=self._fake_client('just prose, no JSON'),
            )

    def test_rejects_empty_caption(self):
        from social_manager.services.caption_generator import (
            CaptionGenerationError, generate_caption,
        )
        listing = self._fake_listing()
        body = '{"caption": "", "hashtags": ["#x"]}'
        with self.assertRaises(CaptionGenerationError):
            generate_caption(
                listing, platform='instagram', client=self._fake_client(body),
            )

    def test_rejects_too_many_hashtags(self):
        from social_manager.services.caption_generator import (
            CaptionGenerationError, generate_caption,
        )
        listing = self._fake_listing()
        tags = ', '.join([f'"#t{i}"' for i in range(13)])
        body = '{"caption": "x", "hashtags": [' + tags + ']}'
        with self.assertRaises(CaptionGenerationError):
            generate_caption(
                listing, platform='instagram', client=self._fake_client(body),
            )

    def test_cost_math_haiku(self):
        from decimal import Decimal
        from social_manager.services.caption_generator import generate_caption
        listing = self._fake_listing()
        body = '{"caption": "x", "hashtags": ["#a"]}'
        result = generate_caption(
            listing, platform='instagram',
            client=self._fake_client(body, input_tokens=1_000_000, output_tokens=200_000),
            model='claude-haiku-4-5',
        )
        # Haiku: $1/MTok in + $5/MTok out. 1M in = $1. 200k out = $1. Total $2.
        self.assertEqual(result['cost_usd'], Decimal('2.000000'))

    def test_unknown_model_cost_zero_with_warning(self):
        from decimal import Decimal
        from social_manager.services.caption_generator import generate_caption
        listing = self._fake_listing()
        body = '{"caption": "x", "hashtags": []}'
        result = generate_caption(
            listing, platform='instagram', client=self._fake_client(body),
            model='mystery-model-9000',
        )
        self.assertEqual(result['cost_usd'], Decimal('0'))


class DraftReviewManualPostViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='staff', password='x', is_staff=True,
        )
        self.client.force_login(self.user)
        self.draft = PostDraft.objects.create(caption='hi', status='approved')

    def test_mark_posted_creates_schedule_and_publishes(self):
        url = reverse('social_manager:review', args=[self.draft.pk])
        resp = self.client.post(url, {'action': 'mark_posted', 'platform': 'instagram'})
        self.assertEqual(resp.status_code, 302)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'published')
        sched = PostSchedule.objects.get(draft=self.draft)
        self.assertEqual(sched.platform_post_id, 'manual')
        self.assertEqual(sched.account.platform, 'instagram')

    def test_mark_posted_rejects_unknown_platform(self):
        url = reverse('social_manager:review', args=[self.draft.pk])
        self.client.post(url, {'action': 'mark_posted', 'platform': 'myspace'})
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'approved')
        self.assertFalse(PostSchedule.objects.filter(draft=self.draft).exists())

    def test_mark_posted_blocked_when_rejected(self):
        self.draft.status = 'rejected'
        self.draft.save()
        url = reverse('social_manager:review', args=[self.draft.pk])
        self.client.post(url, {'action': 'mark_posted', 'platform': 'instagram'})
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'rejected')
        self.assertFalse(PostSchedule.objects.filter(draft=self.draft).exists())
