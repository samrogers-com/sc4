"""Tests for ebay_manager.

Bootstraps the test suite for this app. Initial coverage focuses on
_delete_variant_on_ebay — the helper added in the delete-variant
error-handling refactor — and the html_sanitizer module that backs
the ``|ebay_safe`` template filter.
"""
import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.template import Context, Template
from django.test import TestCase
from django.utils import timezone as dj_timezone

from ebay_manager.models import EbayListing
from ebay_manager.services.html_sanitizer import sanitize_ebay_html
from ebay_manager.services.publish import create_or_update_offer
from ebay_manager.views import _delete_variant_on_ebay


def _resp(status_code, *, json_body=None, text=''):
    """Factory for a mock `requests.Response`-like object."""
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_body if json_body is not None else {}
    r.text = text
    return r


class DeleteVariantOnEbayTests(TestCase):
    """Unit tests for _delete_variant_on_ebay.

    The helper performs up to four eBay side-effects per call:
      1. GET offers for SKU → withdraw + DELETE each
      2. GET item group → PUT (update) or DELETE (if empty)
      3. DELETE inventory item
    It must:
      - short-circuit for drafts
      - error out when the token is missing
      - treat 404 on DELETE as soft-ok (warning, continues)
      - treat 5xx or other 4xx as hard error (returns immediately)
    """

    GROUP_KEY = 'GRP-TEST'

    def _make_active_variant(self, sku='TEST-BOX-1', name='Box 1'):
        return EbayListing.objects.create(
            title='Test title',
            price=100,
            sku=sku,
            status='active',
            is_variant=True,
            group_key=self.GROUP_KEY,
            variant_name=name,
            category_id='261035',
        )

    # --- Short-circuits ---

    def test_draft_variant_no_api_calls(self):
        v = EbayListing.objects.create(
            title='T', price=1, sku='S', status='draft',
            group_key=self.GROUP_KEY, variant_name='Box 1',
        )
        with patch('requests.get') as gget:
            errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        gget.assert_not_called()

    def test_active_without_sku_no_api_calls(self):
        v = EbayListing.objects.create(
            title='T', price=1, sku='', status='active',
            group_key=self.GROUP_KEY, variant_name='Box 1',
        )
        with patch('requests.get') as gget:
            errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        gget.assert_not_called()

    @patch('ebay_manager.services.api_client.get_user_token', return_value=None)
    def test_missing_token_errors(self, _tok):
        v = self._make_active_variant()
        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)
        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('Not authenticated', errors[0])

    # --- Happy path ---

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_happy_path_multi_variant_group(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        # GET /offer?sku=... → one PUBLISHED offer
        # GET /inventory_item_group → group has two SKUs (ours + peer)
        rget.side_effect = [
            _resp(200, json_body={'offers': [{'offerId': 'O1', 'status': 'PUBLISHED'}]}),
            _resp(200, json_body={
                'variantSKUs': ['TEST-BOX-1', 'TEST-BOX-2'],
                'variesBy': {'specifications': [{'name': 'Box', 'values': ['Box 1', 'Box 2']}]},
            }),
        ]
        rpost.return_value = _resp(204)     # withdraw
        rdelete.return_value = _resp(204)   # offer delete + inventory item delete
        rput.return_value = _resp(204)      # group PUT (remaining SKUs)

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        # Group was updated (not deleted) since peer SKU remained
        self.assertEqual(rput.call_count, 1)
        put_url, _ = rput.call_args[0], rput.call_args[1]
        put_body = rput.call_args.kwargs.get('json', {})
        self.assertEqual(put_body['variantSKUs'], ['TEST-BOX-2'])
        self.assertEqual(put_body['variesBy']['specifications'][0]['values'], ['Box 2'])
        # Inventory item delete was called for our SKU
        inv_delete_urls = [c.args[0] for c in rdelete.call_args_list]
        self.assertTrue(any('/inventory_item/TEST-BOX-1' in u for u in inv_delete_urls))

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_last_variant_deletes_item_group(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': []}),  # no offers (already cleaned up)
            _resp(200, json_body={'variantSKUs': ['TEST-BOX-1']}),  # only ours
        ]
        rdelete.return_value = _resp(204)

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        # Item group DELETE was called + inventory item DELETE
        deleted_urls = [c.args[0] for c in rdelete.call_args_list]
        self.assertTrue(any('/inventory_item_group/' in u for u in deleted_urls))
        self.assertTrue(any('/inventory_item/TEST-BOX-1' in u for u in deleted_urls))
        # PUT should NOT have been called (we deleted the group instead)
        rput.assert_not_called()

    # --- Soft-ok paths (404 = already gone) ---

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_offer_already_deleted_is_warning(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': [{'offerId': 'O1', 'status': 'PUBLISHED'}]}),
            _resp(200, json_body={'variantSKUs': ['TEST-BOX-1']}),
        ]
        rpost.return_value = _resp(204)
        # offer DELETE → 404; inventory item DELETE → 204; group DELETE → 204
        rdelete.side_effect = [_resp(404, text='gone'), _resp(204), _resp(204)]

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn('already gone', warnings[0])
        self.assertIn('Delete offer O1', warnings[0])

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_item_group_missing_is_warning(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': []}),
            _resp(404, text='no such group'),
        ]
        rdelete.return_value = _resp(204)

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(errors, [])
        self.assertTrue(any('already gone' in w for w in warnings))
        # Inventory item DELETE still happened
        self.assertEqual(rdelete.call_count, 1)

    # --- Hard-error paths ---

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_offer_delete_500_is_hard_error(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.return_value = _resp(200, json_body={'offers': [{'offerId': 'O1', 'status': 'PUBLISHED'}]})
        rpost.return_value = _resp(204)
        rdelete.return_value = _resp(500, text='boom')

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('500', errors[0])
        # Short-circuits: group and inventory item not touched
        rput.assert_not_called()

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_list_offers_500_is_hard_error(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.return_value = _resp(503, text='eBay is down')

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('503', errors[0])
        rpost.assert_not_called()
        rdelete.assert_not_called()
        rput.assert_not_called()

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_group_get_500_is_hard_error(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': []}),
            _resp(500, text='boom'),
        ]

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('500', errors[0])
        # Inventory item delete should not have been attempted
        rdelete.assert_not_called()
        rput.assert_not_called()

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_inventory_item_delete_500_is_hard_error(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': []}),
            _resp(200, json_body={'variantSKUs': ['TEST-BOX-1']}),
        ]
        # First DELETE: group deletion succeeds. Second DELETE: inventory item fails.
        rdelete.side_effect = [_resp(204), _resp(500, text='boom')]

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('500', errors[0])
        self.assertIn('inventory item', errors[0].lower())

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_group_update_500_is_hard_error(self, rget, rpost, rput, rdelete, _tok):
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': []}),
            _resp(200, json_body={
                'variantSKUs': ['TEST-BOX-1', 'TEST-BOX-2'],
                'variesBy': {'specifications': [{'name': 'Box', 'values': ['Box 1', 'Box 2']}]},
            }),
        ]
        rput.return_value = _resp(500, text='boom')

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(warnings, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('500', errors[0])
        # Inventory item delete should not have been attempted
        rdelete.assert_not_called()

    @patch('ebay_manager.services.api_client.get_user_token', return_value='tok')
    @patch('requests.delete')
    @patch('requests.put')
    @patch('requests.post')
    @patch('requests.get')
    def test_withdraw_failure_is_only_warning(self, rget, rpost, rput, rdelete, _tok):
        """Withdraw is best-effort — a non-2xx there should warn but continue
        to the subsequent DELETE, which is what actually matters."""
        v = self._make_active_variant()
        rget.side_effect = [
            _resp(200, json_body={'offers': [{'offerId': 'O1', 'status': 'PUBLISHED'}]}),
            _resp(200, json_body={'variantSKUs': ['TEST-BOX-1']}),
        ]
        rpost.return_value = _resp(500, text='withdraw exploded')
        rdelete.return_value = _resp(204)

        errors, warnings = _delete_variant_on_ebay(v, self.GROUP_KEY)

        self.assertEqual(errors, [])
        self.assertTrue(any('Withdraw offer O1' in w for w in warnings))


class SanitizeEbayHtmlTests(TestCase):
    """Tests for the html_sanitizer module + |ebay_safe template filter.

    The sanitizer is the mitigation for rendering description_html in
    admin views. Attackers don't currently touch description_html, but
    the filter needs to keep legitimate eBay-style markup intact while
    stripping anything script-bearing.
    """

    # --- legitimate content is preserved ---

    def test_none_and_empty_return_empty_string(self):
        self.assertEqual(sanitize_ebay_html(None), '')
        self.assertEqual(sanitize_ebay_html(''), '')
        self.assertEqual(sanitize_ebay_html(0), '')

    def test_preserves_table_based_ebay_layout(self):
        src = (
            '<table border="2" cellpadding="16" bgcolor="#1c1c1c"'
            ' background="https://media.samscollectibles.net/assets/demim_sc.jpg">'
            '<tr><td><font face="verdana" size="5" color="#87ceeb"><b>Title</b></font></td></tr>'
            '</table>'
        )
        out = sanitize_ebay_html(src)
        # Tag structure preserved
        self.assertIn('<table', out)
        self.assertIn('<font', out)
        self.assertIn('<b>Title</b>', out)
        # Attributes preserved
        self.assertIn('border="2"', out)
        self.assertIn('bgcolor="#1c1c1c"', out)
        self.assertIn('background="https://media.samscollectibles.net/assets/demim_sc.jpg"', out)
        self.assertIn('face="verdana"', out)
        self.assertIn('color="#87ceeb"', out)

    def test_preserves_lists_hr_br_center(self):
        src = '<center><hr><ul><li>One</li><li>Two</li></ul><br></center>'
        out = sanitize_ebay_html(src)
        self.assertIn('<center>', out)
        self.assertIn('<hr', out)
        self.assertIn('<ul>', out)
        self.assertIn('<li>One</li>', out)
        self.assertIn('<br', out)

    def test_preserves_rwr_attribute_on_font(self):
        """<font rwr="1"> is an eBay-proprietary marker used in our templates."""
        out = sanitize_ebay_html('<font rwr="1" size="4">x</font>')
        self.assertIn('rwr="1"', out)

    def test_allows_safe_inline_style(self):
        out = sanitize_ebay_html(
            '<table style="border-spacing:0px; width:100%; max-width:100%;"><tr><td>x</td></tr></table>'
        )
        self.assertIn('border-spacing', out)
        self.assertIn('max-width', out)

    # --- script / handler stripping ---

    def test_strips_script_tags(self):
        # bleach with strip=True removes the <script> element but leaves
        # its text content behind as plain text. The security property
        # we care about is that no executable markup survives — i.e.
        # no <script> tag remains to be parsed and run.
        out = sanitize_ebay_html(
            '<p>before</p><script>alert("xss")</script><p>after</p>'
        )
        self.assertNotIn('<script', out)
        self.assertNotIn('</script', out)
        self.assertIn('before', out)
        self.assertIn('after', out)

    def test_strips_event_handler_attributes(self):
        out = sanitize_ebay_html('<b onclick="alert(1)">click</b>')
        self.assertNotIn('onclick', out)
        self.assertIn('<b>click</b>', out)

    def test_strips_javascript_href(self):
        out = sanitize_ebay_html('<a href="javascript:alert(1)">go</a>')
        self.assertNotIn('javascript', out)
        self.assertNotIn('alert', out)

    def test_strips_data_uri_image_src(self):
        # data: URIs can carry script in SVG payloads; block entirely.
        out = sanitize_ebay_html('<img src="data:image/svg+xml;base64,PHN2Zz4=">')
        self.assertNotIn('data:', out)

    def test_strips_iframe_and_object(self):
        out = sanitize_ebay_html('<iframe src="https://evil.example"></iframe><object></object>')
        self.assertNotIn('<iframe', out)
        self.assertNotIn('<object', out)

    def test_strips_style_tag(self):
        out = sanitize_ebay_html('<style>body{background:url(javascript:alert(1))}</style><p>ok</p>')
        self.assertNotIn('<style', out)
        self.assertIn('ok', out)

    def test_strips_expression_in_inline_css(self):
        out = sanitize_ebay_html(
            '<div style="width: expression(alert(1)); color: red;">x</div>'
        )
        # div isn't in the allowlist — whole element dropped; regardless,
        # the expression() payload must not survive.
        self.assertNotIn('expression', out)
        self.assertNotIn('alert', out)

    def test_strips_html_comments(self):
        out = sanitize_ebay_html('<p>ok</p><!-- <script>alert(1)</script> -->')
        self.assertNotIn('<!--', out)
        self.assertNotIn('alert', out)

    # --- template filter integration ---

    def test_filter_marks_output_safe_and_sanitizes(self):
        t = Template("{% load ebay_html %}{{ bad|ebay_safe }}")
        rendered = t.render(Context({'bad': '<b>hi</b><script>alert(1)</script>'}))
        self.assertIn('<b>hi</b>', rendered)
        self.assertNotIn('<script', rendered)
        self.assertNotIn('</script', rendered)

    def test_filter_handles_none(self):
        t = Template("{% load ebay_html %}{{ missing|ebay_safe }}")
        rendered = t.render(Context({'missing': None}))
        self.assertEqual(rendered.strip(), '')


class CreateOrUpdateOfferPayloadTests(TestCase):
    """Tests for create_or_update_offer payload construction.

    These tests cover the format-branching added with auction support.
    They patch requests.get/post so the offer-create POST is the only
    network call we observe — the assertions inspect the JSON body that
    would be sent to eBay.
    """

    def _make_listing(self, **overrides):
        defaults = dict(
            title='Test listing',
            price=Decimal('19.95'),
            quantity=1,
            category_id='261035',
            sku='TEST-SKU-1',
            description_html='<p>desc</p>',
            packaging_config='sealed_box',
        )
        defaults.update(overrides)
        return EbayListing.objects.create(**defaults)

    @patch('ebay_manager.services.publish.get_user_token', return_value='tok')
    @patch('ebay_manager.services.publish.requests.post')
    @patch('ebay_manager.services.publish.requests.get')
    def test_fixed_price_payload_unchanged(self, rget, rpost, _tok):
        """Regression: existing FIXED_PRICE payload shape is preserved."""
        listing = self._make_listing()
        rget.return_value = MagicMock(status_code=200, **{'json.return_value': {'offers': []}})
        rpost.return_value = MagicMock(
            status_code=201, **{'json.return_value': {'offerId': 'OFFER-1'}}
        )

        offer_id = create_or_update_offer(listing, listing.sku)

        self.assertEqual(offer_id, 'OFFER-1')
        body = rpost.call_args.kwargs['json']
        self.assertEqual(body['format'], 'FIXED_PRICE')
        self.assertEqual(body['pricingSummary'], {
            'price': {'value': '19.95', 'currency': 'USD'},
        })
        self.assertEqual(body['availableQuantity'], 1)
        # FIXED_PRICE + GTC default → no listingDuration in payload
        self.assertNotIn('listingDuration', body)
        self.assertNotIn('scheduledStartDate', body)
        # Existing core fields still present
        self.assertEqual(body['sku'], 'TEST-SKU-1')
        self.assertEqual(body['marketplaceId'], 'EBAY_US')
        self.assertEqual(body['categoryId'], '261035')
        self.assertEqual(body['merchantLocationKey'], 'SC-DEFAULT')
        self.assertIn('listingPolicies', body)

    @patch('ebay_manager.services.publish.get_user_token', return_value='tok')
    @patch('ebay_manager.services.publish.requests.post')
    @patch('ebay_manager.services.publish.requests.get')
    def test_auction_payload_basic(self, rget, rpost, _tok):
        """AUCTION format produces auctionStartPrice + listingDuration."""
        listing = self._make_listing(
            listing_format='AUCTION',
            listing_duration='DAYS_7',
            auction_start_price=Decimal('14.95'),
            quantity=5,  # should be coerced to 1 in payload
        )
        rget.return_value = MagicMock(status_code=200, **{'json.return_value': {'offers': []}})
        rpost.return_value = MagicMock(
            status_code=201, **{'json.return_value': {'offerId': 'OFFER-A'}}
        )

        create_or_update_offer(listing, listing.sku)

        body = rpost.call_args.kwargs['json']
        self.assertEqual(body['format'], 'AUCTION')
        self.assertEqual(body['listingDuration'], 'DAYS_7')
        self.assertEqual(body['availableQuantity'], 1)
        self.assertEqual(body['pricingSummary'], {
            'auctionStartPrice': {'value': '14.95', 'currency': 'USD'},
        })
        # No reserve price set → key omitted
        self.assertNotIn('auctionReservePrice', body['pricingSummary'])
        # No scheduled start → key omitted
        self.assertNotIn('scheduledStartDate', body)

    @patch('ebay_manager.services.publish.get_user_token', return_value='tok')
    @patch('ebay_manager.services.publish.requests.post')
    @patch('ebay_manager.services.publish.requests.get')
    def test_auction_falls_back_to_price_when_no_start_price(self, rget, rpost, _tok):
        listing = self._make_listing(
            listing_format='AUCTION',
            listing_duration='DAYS_3',
            # auction_start_price intentionally None
        )
        rget.return_value = MagicMock(status_code=200, **{'json.return_value': {'offers': []}})
        rpost.return_value = MagicMock(
            status_code=201, **{'json.return_value': {'offerId': 'OFFER-B'}}
        )

        create_or_update_offer(listing, listing.sku)

        body = rpost.call_args.kwargs['json']
        self.assertEqual(
            body['pricingSummary']['auctionStartPrice'],
            {'value': '19.95', 'currency': 'USD'},
        )

    @patch('ebay_manager.services.publish.get_user_token', return_value='tok')
    @patch('ebay_manager.services.publish.requests.post')
    @patch('ebay_manager.services.publish.requests.get')
    def test_auction_with_reserve_price(self, rget, rpost, _tok):
        listing = self._make_listing(
            listing_format='AUCTION',
            listing_duration='DAYS_7',
            auction_start_price=Decimal('9.99'),
            auction_reserve_price=Decimal('25.00'),
        )
        rget.return_value = MagicMock(status_code=200, **{'json.return_value': {'offers': []}})
        rpost.return_value = MagicMock(
            status_code=201, **{'json.return_value': {'offerId': 'OFFER-C'}}
        )

        create_or_update_offer(listing, listing.sku)

        body = rpost.call_args.kwargs['json']
        self.assertEqual(
            body['pricingSummary']['auctionReservePrice'],
            {'value': '25.00', 'currency': 'USD'},
        )

    @patch('ebay_manager.services.publish.get_user_token', return_value='tok')
    @patch('ebay_manager.services.publish.requests.post')
    @patch('ebay_manager.services.publish.requests.get')
    def test_auction_with_scheduled_start_time_iso8601(self, rget, rpost, _tok):
        # 2026-05-03 18:05:00 US/Pacific → 2026-05-04 01:05:00 UTC (PDT, UTC-7)
        pacific = datetime.timezone(datetime.timedelta(hours=-7))
        scheduled = datetime.datetime(2026, 5, 3, 18, 5, 0, tzinfo=pacific)
        listing = self._make_listing(
            listing_format='AUCTION',
            listing_duration='DAYS_7',
            auction_start_price=Decimal('14.95'),
            scheduled_start_time=scheduled,
        )
        rget.return_value = MagicMock(status_code=200, **{'json.return_value': {'offers': []}})
        rpost.return_value = MagicMock(
            status_code=201, **{'json.return_value': {'offerId': 'OFFER-D'}}
        )

        create_or_update_offer(listing, listing.sku)

        body = rpost.call_args.kwargs['json']
        self.assertEqual(body['scheduledStartDate'], '2026-05-04T01:05:00.000Z')

    @patch('ebay_manager.services.publish.get_user_token', return_value='tok')
    @patch('ebay_manager.services.publish.requests.post')
    @patch('ebay_manager.services.publish.requests.get')
    def test_fixed_price_with_explicit_duration_includes_it(self, rget, rpost, _tok):
        """A FIXED_PRICE listing with a non-GTC duration should include
        listingDuration in the payload (rare, but supported by eBay)."""
        listing = self._make_listing(
            listing_format='FIXED_PRICE',
            listing_duration='DAYS_7',
        )
        rget.return_value = MagicMock(status_code=200, **{'json.return_value': {'offers': []}})
        rpost.return_value = MagicMock(
            status_code=201, **{'json.return_value': {'offerId': 'OFFER-E'}}
        )

        create_or_update_offer(listing, listing.sku)

        body = rpost.call_args.kwargs['json']
        self.assertEqual(body['format'], 'FIXED_PRICE')
        self.assertEqual(body['listingDuration'], 'DAYS_7')
