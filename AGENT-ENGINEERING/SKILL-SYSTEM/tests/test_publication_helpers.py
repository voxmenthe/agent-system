"""Boundary tests for publication browser helpers, without a live browser."""
import importlib.util
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(site):
    path = ROOT / 'skills' / site / 'scripts' / 'news_research.py'
    spec = importlib.util.spec_from_file_location('publication_' + site, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicationHelperTests(unittest.TestCase):
    def test_url_boundary_precedes_browser_access(self):
        for site, domain in [('nyt', 'www.nytimes.com'), ('washp', 'www.washingtonpost.com')]:
            helper = load(site)
            for url in [f'http://{domain}/x', f'https://{domain}.evil.test/x',
                        f'https://user:pass@{domain}/x', f'https://{domain}/x?token=secret',
                        f'https://{domain}/x#fragment', f'https://{domain}:444/x']:
                with self.subTest(site=site, url=url), patch.object(helper, 'apple') as apple:
                    with self.assertRaises(helper.BrowserError) as ctx:
                        helper.validate_url(url)
                    self.assertEqual(ctx.exception.code, 64)
                    apple.assert_not_called()
            self.assertEqual(helper.validate_url(f'https://{domain}/2026/09/06/story/'),
                             f'https://{domain}/2026/09/06/story/')

    def test_timeout_is_transport_failure_not_logout(self):
        for site in ['nyt', 'washp']:
            helper = load(site)
            with patch.object(helper.subprocess, 'run', side_effect=subprocess.TimeoutExpired('osascript',40)):
                with self.assertRaises(helper.BrowserError) as ctx:
                    helper.apple('ignored')
                self.assertEqual(ctx.exception.code, 12)

    def test_disabled_javascript_is_distinct(self):
        helper = load('nyt')
        result = subprocess.CompletedProcess([], 1, '', 'Allow JavaScript from Apple Events')
        with patch.object(helper.subprocess, 'run', return_value=result):
            with self.assertRaises(helper.BrowserError) as ctx:
                helper.apple('ignored')
            self.assertEqual(ctx.exception.code, 11)

    def test_ambiguous_windows_do_not_create_tabs(self):
        helper = load('washp')
        from argparse import Namespace
        with patch.object(helper, 'windows', return_value=[1,2]), patch.object(helper, 'apple') as apple:
            with self.assertRaises(helper.BrowserError) as ctx:
                helper.run(Namespace(window_id=None))
            self.assertEqual(ctx.exception.code, 12)
            apple.assert_not_called()

    def test_created_tab_is_cleaned_up_after_extraction_failure(self):
        helper = load('nyt')
        from argparse import Namespace
        calls = []
        def apple(script):
            calls.append(script)
            if 'make new tab' in script:
                return '123'
            if 'javascript' in script:
                raise helper.BrowserError('failed')
            return ''
        with patch.object(helper, 'windows', return_value=[1]), patch.object(helper, 'apple', side_effect=apple), patch.object(helper.time, 'sleep'):
            with self.assertRaises(helper.BrowserError):
                helper.run(Namespace(window_id=1, command='status'))
        self.assertIn('close (first tab', calls[-1])
        self.assertIn('123', calls[-1])


if __name__ == '__main__':
    unittest.main()
