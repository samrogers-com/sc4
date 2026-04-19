"""Marketing dashboard — staff-only views for draft generation + review.

Flow:
    1. DraftListView — queue of all drafts (filterable by status/platform)
    2. GenerateDraftView — pick listing + platform → Haiku generates → saves PostDraft
    3. DraftReviewView — edit caption/hashtags, approve/reject, publish stubs
    4. PublishView — per-platform publish; returns "connect OAuth first" until each
       platform's adapter is wired (see docs/social-oauth-setup.md)
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

from ebay_manager.models import EbayListing

from .models import PostDraft, SocialAccount
from .services.caption_generator import CaptionGenerationError, generate_caption


PLATFORM_CHOICES = [c[0] for c in SocialAccount.PLATFORM_CHOICES]
PLATFORM_LABELS = dict(SocialAccount.PLATFORM_CHOICES)


@method_decorator(staff_member_required, name='dispatch')
class DraftListView(View):
    """List all PostDrafts with filters."""

    template_name = 'social_manager/draft_list.html'

    def get(self, request):
        drafts = PostDraft.objects.select_related('listing').order_by('-created_at')
        status = request.GET.get('status')
        if status:
            drafts = drafts.filter(status=status)
        ctx = {
            'drafts': drafts,
            'status_filter': status,
            'status_choices': PostDraft.STATUS_CHOICES,
            'platforms': PLATFORM_CHOICES,
        }
        return render(request, self.template_name, ctx)


@method_decorator(staff_member_required, name='dispatch')
class GenerateDraftView(View):
    """Generate a new draft for a listing + platform."""

    template_name = 'social_manager/draft_generate.html'

    def get(self, request):
        listings = EbayListing.objects.filter(status='active').order_by('title')[:200]
        ctx = {
            'listings': listings,
            'platforms': PLATFORM_CHOICES,
            'platform_labels': PLATFORM_LABELS,
            'prefill_listing_id': request.GET.get('listing'),
            'prefill_platform': request.GET.get('platform'),
        }
        return render(request, self.template_name, ctx)

    def post(self, request):
        listing_id = request.POST.get('listing_id')
        platform = request.POST.get('platform')
        model = request.POST.get('model') or 'claude-haiku-4-5'

        if not listing_id or not platform:
            messages.error(request, 'Pick both a listing and a platform.')
            return redirect('social_manager:generate')
        if platform not in PLATFORM_CHOICES:
            messages.error(request, f'Unknown platform: {platform}')
            return redirect('social_manager:generate')

        listing = get_object_or_404(EbayListing, pk=listing_id)
        try:
            result = generate_caption(listing, platform=platform, model=model)
        except CaptionGenerationError as exc:
            messages.error(request, f'Generation failed: {exc}')
            return redirect('social_manager:generate')

        draft = PostDraft.objects.create(
            listing=listing,
            caption=result['caption'],
            hashtags=' '.join(result['hashtags']),
            llm_model_used=model,
            generation_cost_usd=result['cost_usd'],
            status='pending',
        )
        messages.success(
            request,
            f'Draft created for {listing.title[:50]} on {PLATFORM_LABELS[platform]} '
            f'(${result["cost_usd"]}).',
        )
        return redirect('social_manager:review', pk=draft.pk)


@method_decorator(staff_member_required, name='dispatch')
class DraftReviewView(View):
    """Review, edit, approve/reject, and trigger per-platform publish stubs."""

    template_name = 'social_manager/draft_review.html'

    def get(self, request, pk):
        draft = get_object_or_404(PostDraft, pk=pk)
        accounts = {a.platform: a for a in SocialAccount.objects.filter(is_active=True)}
        ctx = {
            'draft': draft,
            'platforms': PLATFORM_CHOICES,
            'platform_labels': PLATFORM_LABELS,
            'accounts': accounts,
        }
        return render(request, self.template_name, ctx)

    def post(self, request, pk):
        draft = get_object_or_404(PostDraft, pk=pk)
        action = request.POST.get('action')
        if action == 'save':
            draft.caption = request.POST.get('caption', draft.caption)
            draft.hashtags = request.POST.get('hashtags', draft.hashtags)
            draft.notes = request.POST.get('notes', draft.notes)
            draft.save()
            messages.success(request, 'Changes saved.')
        elif action == 'approve':
            from django.utils import timezone
            draft.status = 'approved'
            draft.approved_at = timezone.now()
            draft.save()
            messages.success(request, 'Approved. Publish when ready.')
        elif action == 'reject':
            draft.status = 'rejected'
            draft.save()
            messages.success(request, 'Rejected.')
        else:
            messages.error(request, f'Unknown action: {action}')
        return redirect('social_manager:review', pk=pk)


@method_decorator(staff_member_required, name='dispatch')
class PublishView(View):
    """Publish to a specific platform, or to all approved platforms.

    Until each platform's OAuth + publish adapter is wired (see
    docs/social-oauth-setup.md), this returns an honest "connect first"
    message. One platform at a time lands in follow-up PRs.
    """

    def post(self, request, pk, platform):
        draft = get_object_or_404(PostDraft, pk=pk)
        if draft.status not in {'approved', 'scheduled'}:
            messages.error(request, 'Approve the draft before publishing.')
            return redirect('social_manager:review', pk=pk)

        if platform == 'all':
            messages.info(
                request,
                'Publish-to-all is queued for Phase-3 wiring. For now, publish '
                'to each platform individually once its OAuth is connected.',
            )
            return redirect('social_manager:review', pk=pk)

        if platform not in PLATFORM_CHOICES:
            messages.error(request, f'Unknown platform: {platform}')
            return redirect('social_manager:review', pk=pk)

        account = SocialAccount.objects.filter(platform=platform, is_active=True).first()
        if not account or not account.access_token:
            messages.warning(
                request,
                f'{PLATFORM_LABELS[platform]} is not connected yet. See '
                f'docs/social-oauth-setup.md for setup steps, then come back here.',
            )
            return redirect('social_manager:review', pk=pk)

        # Real publish logic lands per-platform in follow-up PRs
        messages.info(
            request,
            f'{PLATFORM_LABELS[platform]} OAuth is connected but publish '
            f'adapter is not yet wired in this PR. See docs/social-oauth-setup.md '
            f'for the follow-up PR roadmap.',
        )
        return redirect('social_manager:review', pk=pk)
