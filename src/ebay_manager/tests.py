"""Tests for ebay_manager.

Bootstraps the test suite for this app. Initial coverage focuses on
_delete_variant_on_ebay — the helper added in the delete-variant
error-handling refactor.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from ebay_manager.models import EbayListing
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
