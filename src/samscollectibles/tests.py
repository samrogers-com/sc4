"""Tests for the public contact form's anti-spam layers.

Mirrors the four defenses in samscollectibles.spam_filters: honeypot,
rate-limit, Turnstile (skipped without secret), content filter.
"""
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from samscollectibles import spam_filters


class ContentFilterTests(TestCase):
    def test_random_gibberish_message_blocked(self):
        # Real spam from prod 2026-04-25
        self.assertTrue(spam_filters.is_spam_content(
            'rtiewngszp', '', 'oyvuzqzzokephomneldtumjjrdnzor',
        ))

    def test_random_gibberish_name_blocked(self):
        self.assertTrue(spam_filters.is_spam_content(
            'qwzxcvbnmasdfghjkl', '', 'Hello, I want to ask about a comic.',
        ))

    def test_short_message_blocked(self):
        self.assertTrue(spam_filters.is_spam_content('Sam', '', 'hi'))

    def test_no_latin_letters_blocked(self):
        self.assertTrue(spam_filters.is_spam_content('Sam', '', '日本語のメッセージです'))

    def test_known_spam_phrase_blocked(self):
        self.assertTrue(spam_filters.is_spam_content(
            'Sam', '', 'Just writing about your the prices for items',
        ))

    def test_legit_message_passes(self):
        self.assertFalse(spam_filters.is_spam_content(
            'Jane Doe', '',
            'Hi Sam, I saw your Howard the Duck box. Is the seal intact?',
        ))

    def test_short_greeting_with_punctuation_passes(self):
        # 14 chars, no spaces, but has punctuation — looks like an email/url
        self.assertFalse(spam_filters.is_spam_content(
            'Pat', '', 'jane@example.com',
        ))


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_first_three_pass(self):
        for _ in range(3):
            self.assertFalse(spam_filters.is_rate_limited('1.2.3.4'))

    def test_fourth_blocked(self):
        for _ in range(3):
            spam_filters.is_rate_limited('1.2.3.4')
        self.assertTrue(spam_filters.is_rate_limited('1.2.3.4'))

    def test_other_ip_unaffected(self):
        for _ in range(5):
            spam_filters.is_rate_limited('1.2.3.4')
        self.assertFalse(spam_filters.is_rate_limited('5.6.7.8'))


class TurnstileTests(TestCase):
    @override_settings(TURNSTILE_SECRET_KEY='')
    def test_unconfigured_passes(self):
        # Turnstile disabled = always pass (other layers still active)
        self.assertTrue(spam_filters.verify_turnstile('any-token', '1.2.3.4'))


class ContactViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse('contact')

    def test_get_renders(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_legit_submission_sends_email(self):
        resp = self.client.post(self.url, {
            'name': 'Jane Doe',
            'email': 'jane@example.com',
            'message': 'Hi Sam, do you ship internationally?',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Jane Doe', mail.outbox[0].body)

    def test_honeypot_silently_drops(self):
        resp = self.client.post(self.url, {
            'name': 'Jane',
            'email': 'jane@example.com',
            'message': 'A real-looking message.',
            'website': 'http://spam.example.com',  # bot fills the trap
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_random_gibberish_silently_dropped(self):
        resp = self.client.post(self.url, {
            'name': 'rtiewngszp',
            'email': 'jsfnefrl@immenseignite.info',
            'message': 'oyvuzqzzokephomneldtumjjrdnzor',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_rate_limit_blocks_4th(self):
        for i in range(3):
            self.client.post(self.url, {
                'name': f'Jane{i}',
                'email': f'jane{i}@example.com',
                'message': f'Real-looking message number {i}.',
            })
        self.assertEqual(len(mail.outbox), 3)
        self.client.post(self.url, {
            'name': 'Jane4',
            'email': 'jane4@example.com',
            'message': 'A fourth real-looking message.',
        })
        # 4th should not have sent mail
        self.assertEqual(len(mail.outbox), 3)
