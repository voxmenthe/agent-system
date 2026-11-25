#!/usr/bin/env python3
"""Read rendered publication pages through existing Chrome; no session-store access."""
import argparse
import fcntl
import json
import re
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode, urlsplit

SITE = Path(__file__).resolve().parents[1].name
DOMAIN = {'nyt': 'www.nytimes.com', 'washp': 'www.washingtonpost.com'}[SITE]
HOME_URL = 'https://' + DOMAIN + '/'
class BrowserError(Exception):
    def __init__(self, message, code=12):
        super().__init__(message)
        self.code = code

def apple(script):
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        raise BrowserError('AppleScript timed out; browser targeting failure, not an authentication verdict.')
    if result.returncode:
        disabled = 'Allow JavaScript from Apple Events' in result.stderr
        code = re.search(r'\((-?\d+)\)\s*$', result.stderr)
        diagnostic = (' AppleScript error ' + code.group(1) + '.') if code else ''
        raise BrowserError('JavaScript from Apple Events disabled.' if disabled else 'Chrome automation failed.' + diagnostic + ' Inspect Chrome responsiveness and automation permissions.', 11 if disabled else 12)
    return result.stdout.strip()

def validate_url(url):
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname not in {DOMAIN, DOMAIN.removeprefix('www.')} or u.username or u.password or u.port not in (None,443):
        raise BrowserError('Use a canonical HTTPS article URL on ' + DOMAIN, 64)
    if u.query or u.fragment:
        raise BrowserError('Remove query strings and fragments; do not pass gift/access tokens.', 64)
    return url

def windows(window_id=None):
    # Return only window IDs; do not emit unrelated URLs or query strings.
    selection = f'{{first window whose id is {int(window_id)}}}' if window_id else 'windows'
    return [int(x) for x in apple(f'''
tell application "Google Chrome"
 set found to {{}}
 repeat with w in {selection}
  repeat with t in tabs of w
   try
    set u to URL of t
    if u starts with "https://{DOMAIN}/" then
    if (id of w) is not in found then set end of found to id of w
    end if
   end try
  end repeat
 end repeat
 set resultText to ""
 repeat with wid in found
  set resultText to resultText & (wid as text) & linefeed
 end repeat
 return resultText
end tell
''').splitlines() if x.isdigit()]

def run(args):
    candidates = windows(args.window_id)
    if args.window_id:
        if args.window_id not in candidates:
            raise BrowserError('Selected window has no existing publication tab. Open the site in the intended signed-in Chrome window.')
        wid = args.window_id
    elif len(candidates) == 1:
        wid = candidates[0]
    else:
        raise BrowserError('Select --window-id from existing publication windows: ' + str(candidates) + '. If empty, open the site in the intended Chrome profile.')
    url = HOME_URL
    if args.command == 'article':
        url = validate_url(args.value)
    elif args.command == 'search':
        url = HOME_URL + ('search?' + urlencode({'query':args.value}) if SITE == 'nyt' else 'search/?' + urlencode({'query':args.value}))
    tid = int(apple(f'tell application "Google Chrome" to get id of (make new tab at end of tabs of (first window whose id is {wid}) with properties {{URL:{json.dumps(url)}}})'))
    target = f'(first tab of (first window whose id is {wid}) whose id is {tid})'
    try:
        source = (Path(__file__).with_name('extract.js')).read_text()
        js = 'JSON.stringify((' + source + ')())'
        data = None
        for attempt in range(12):
            time.sleep(1)
            raw = apple(f'tell application "Google Chrome" to execute {target} javascript {json.dumps(js)}')
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if data['access']['challenge'] or data['access']['gate']:
                break
            if urlsplit(data['url']).hostname in {DOMAIN,DOMAIN.removeprefix('www.')} and (data['paragraphCount'] if args.command == 'article' else data['stories']):
                # Allow the header and access gate to finish hydration before extraction.
                time.sleep(3)
                data = json.loads(apple(f'tell application "Google Chrome" to execute {target} javascript {json.dumps(js)}'))
                break
        if not data or urlsplit(data['url']).hostname not in {DOMAIN,DOMAIN.removeprefix('www.')}:
            raise BrowserError('Page did not load on the expected publication domain.')
        if args.command != 'article' or args.metadata_only:
            data.pop('paragraphs', None)
        else:
            text = '\n\n'.join(data.pop('paragraphs', []))
            data['text'] = text[:args.max_characters]
            data['truncatedText'] = len(text) > args.max_characters
        data['command'] = args.command
        print(json.dumps(data, ensure_ascii=False))
        if data['access']['challenge']:
            return 13
        if data['access']['gate'] or data['access']['signedOut']:
            return 10
        if args.command == 'article' and not data['paragraphCount']:
            return 14
        return 0
    finally:
        try:
            apple(f'tell application "Google Chrome" to close {target}')
        except BrowserError as exc:
            print('Disposable tab cleanup failed: ' + str(exc), file=sys.stderr)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window-id', type=int)
    p.add_argument('--metadata-only', action='store_true')
    p.add_argument('--max-characters', type=int, default=12000)
    p.add_argument('command', choices=['status','frontpage','search','article'])
    p.add_argument('value', nargs='?')
    a = p.parse_args()
    if a.command in {'article','search'} and not a.value:
        p.error('article/search requires a URL/query')
    if a.max_characters < 1:
        p.error('--max-characters must be positive')
    if a.command == 'article':
        validate_url(a.value)
    state = Path.home() / '.codex/state/publication-research'
    state.mkdir(parents=True,exist_ok=True)
    with (state / 'browser.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return run(a)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except BrowserError as exc:
        print(json.dumps({'error':str(exc),'exit':exc.code}), file=sys.stderr)
        sys.exit(exc.code)
