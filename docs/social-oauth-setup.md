# Social Platform OAuth Setup

The Marketing dashboard (`/social/`) generates and edits drafts today but can't actually publish them until each platform's OAuth is connected and its publish adapter is wired. This doc is the roadmap, in **priority order**.

Each platform is a separate follow-up PR. Sam should pick the next platform to wire based on where he's willing to invest setup time vs. what gives the highest return.

## Priority ranking

Prioritized by **(1) API maturity**, **(2) alignment with Sam's content style**, **(3) audience match for vintage non-sport cards**, and **(4) legal/regulatory stability**.

| Rank | Platform | Why this order | Setup difficulty | Real-publish effort |
|---|---|---|---|---|
| **#1** | **Instagram** | Best-documented API (Meta Graph). Visual-first matches the product (card photos). Reels are boosted for small accounts. Direct integration with eBay Seller Hub Social Page. | Medium — Meta Developer app + Business account + OAuth | ~1 day |
| **#2** | **Reddit** | Simple PRAW library, OAuth straightforward. Engaged niche communities (r/nonsportcards, r/tradingcards). No hard-sell pressure. | Easy | ~0.5 day |
| **#3** | **Pinterest** | Passive SEO value — pins show up in Google image search. Low effort to auto-pin listing images. | Easy | ~0.5 day |
| **#4** | **Facebook (Pages)** | Graph API works for Pages. **⚠️ API access to Groups is extremely restricted since 2018 — auto-posting to groups is NOT possible for most developers.** Marketing plan's Group-centric approach is a manual task. | Medium | ~1 day (Pages only) |
| **#5** | **YouTube** | Data API is mature but requires actual video content, which Sam doesn't have yet. Wire later, when videos exist. | Medium | ~1-2 days |
| **❌** | **TikTok** | Skip — regulatory uncertainty per marketing plan §1; Content Posting API requires approval that may never come for a small US business. Instagram Reels covers the same audience without the risk. | Blocked | N/A |

## #1 — Instagram (recommended first)

### Prerequisites
- An Instagram Business or Creator account (not personal)
- A Facebook Page linked to it (Meta requires this)

### Steps

1. **Create a Meta Developer app** at https://developers.facebook.com/apps
   - App type: "Business"
   - Add the **Instagram Graph API** product
   - Add the **Facebook Login for Business** product
2. **Configure OAuth redirect URI** in the app settings:
   - `https://samscollectibles.net/social/oauth/instagram/callback/`
3. **App review / permissions** — request these scopes:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
4. **Add credentials to Ansible vault**:
   ```yaml
   vault_instagram_client_id: "..."
   vault_instagram_client_secret: "..."
   ```
5. **Merge the follow-up Instagram PR** (not yet written) — wires the OAuth callback + publish adapter
6. **In Marketing dashboard**: click "Connect Instagram" on the Social Account page → complete OAuth → token stored in DB
7. **Test post**: generate a draft, approve, click "Publish to Instagram"

### What the publish adapter will do (pending PR)

```python
def publish_instagram(draft, account):
    # 1. Upload the image to Meta's container API
    container = requests.post(
        f'https://graph.facebook.com/v20.0/{account.ig_user_id}/media',
        data={'image_url': draft.image_url, 'caption': draft.caption + ' ' + draft.hashtags,
              'access_token': account.access_token},
    ).json()
    # 2. Publish the container
    publish = requests.post(
        f'https://graph.facebook.com/v20.0/{account.ig_user_id}/media_publish',
        data={'creation_id': container['id'], 'access_token': account.access_token},
    )
    return publish.json()['id']
```

## #2 — Reddit

### Prerequisites
- Reddit account

### Steps
1. Create a Reddit app at https://www.reddit.com/prefs/apps (type: "script")
2. Note the client_id + secret
3. Vault entries + follow-up PR wires PRAW
4. Post rules matter a lot: r/nonsportcards allows collection posts but bans sales links; r/tradingcards is stricter. The publish adapter should respect per-subreddit rules.

## #3 — Pinterest

Similar Developer-app → OAuth → Pin Creation API flow. Low effort.

## #4 — Facebook Pages (not Groups)

**Important:** Meta's Graph API supports posting to Pages you admin, but **auto-posting to Groups** is not available except for a narrow set of pre-approved business integrations. Sam's marketing plan §1 ranked Facebook Groups #1 as a *manual posting* channel — that stays manual. The dashboard's "Facebook" button would post to the business Page, which is a different (and smaller) audience.

## #5 — YouTube

Defer until Sam has video content to post. API is well-documented but needs the actual media pipeline.

## Rotation + revocation

For all platforms:
- Store OAuth tokens in `SocialAccount.access_token` (already DB-backed)
- Track expiry in `SocialAccount.token_expiry`
- Add a management command `check_token_expiry` that emails Sam 7 days before any token expires
- Rotation path: re-run the OAuth flow from the dashboard — overwrites existing row

## Follow-up PR roadmap

| PR title | Depends on |
|---|---|
| Wire Instagram publish adapter + OAuth callback | This PR + Meta Developer app |
| Wire Reddit publish adapter + OAuth | Reddit app |
| Wire Pinterest publish adapter + OAuth | Pinterest Developer app |
| Wire Facebook Pages publish adapter | Meta Developer app (already done for IG) |
| Token-expiry warning email | any single OAuth PR |

Sam: let me know which platform to tackle first after this PR lands and I'll start the next.
