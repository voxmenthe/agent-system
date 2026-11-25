"""Offline contracts for the bookmarks skill's page helper and CLI.

The page helper runs in Node against simulated X responses; its export then
feeds the CLI, which is the same seam a live capture crosses.
"""
from __future__ import annotations

import hashlib
import http.server
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "bookmarks" / "scripts"
HELPER = SCRIPTS / "x-folder.js"
CLI = SCRIPTS / "bookmarks.py"
FOLDER = "1937566408268988861"
C1 = "-1791633600000"  # 2026-10-10T12:00:00Z
C2 = "-1791201600000"  # 2026-10-05T12:00:00Z

HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const [helperPath, scenarioPath] = process.argv.slice(1);
const scenario = JSON.parse(fs.readFileSync(scenarioPath, 'utf8'));
class FakeXHR {
  constructor() { this.listeners = []; }
  open() {}
  send() {}
  addEventListener(type, fn) { if (type === 'load') this.listeners.push(fn); }
}
const ctx = {
  XMLHttpRequest: FakeXHR, fetch: async () => { throw new Error('no network'); },
  location: new URL('https://x.com' + scenario.path), history: { pushState() {} },
  dispatchEvent() {}, PopStateEvent: class {}, KeyboardEvent: class {}, URL, setTimeout, console, innerHeight: 900,
  document: { querySelector: () => null, querySelectorAll: () => [], getElementById: () => null },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(helperPath, 'utf8'), ctx);
const serve = responses => responses.forEach(r => {
  const xhr = new ctx.XMLHttpRequest();
  xhr.open('GET', r.url);
  xhr.send();
  Object.assign(xhr, { status: r.status, responseText: r.body });
  xhr.listeners.forEach(fn => fn());
});
(async () => {
  serve(scenario.responses);
  const out = { full: ctx.__xb.json(), first: ctx.__xb.json({ pages: 1 }), thread: await ctx.__xb.thread('500') };
  serve(scenario.later);
  out.revealed = await ctx.__xb.thread('500');
  process.stdout.write(JSON.stringify(out));
})();
"""


def tweet(post_id, handle, created, text, *, urls=(), media=(), note=None, quoted=None, reply_to=None, card=None):
    legacy = {
        "created_at": created,
        "full_text": text,
        "entities": {"urls": [{"url": s, "expanded_url": e} for s, e in urls],
                     "media": [{"url": m["tco"]} for m in media]},
        "extended_entities": {"media": [m["media"] for m in media]},
        "in_reply_to_status_id_str": reply_to,
        "conversation_id_str": post_id,
    }
    result = {"__typename": "Tweet", "rest_id": post_id,
              "core": {"user_results": {"result": {"core": {"screen_name": handle}}}}, "legacy": legacy}
    if note:
        result["note_tweet"] = {"note_tweet_results": {"result": {"text": note, "entity_set": {"urls": []}}}}
    if quoted:
        result["quoted_status_result"] = {"result": quoted}
    if card:
        result["card"] = {"legacy": {"binding_values": [{"key": "card_url", "value": {"string_value": card}}]}}
    return result


def item(post_id, result):
    return {"entryId": f"tweet-{post_id}", "content": {"itemContent": {"tweet_results": {"result": result}}}}


def folder_response(entries, bottom, cursor=None, folder=FOLDER, status=200):
    variables = {"bookmark_collection_id": folder, "count": 20, **({"cursor": cursor} if cursor else {})}
    entries = [*entries, {"entryId": "cursor-top-1", "content": {"value": "top"}}]
    if bottom:
        entries.append({"entryId": "cursor-bottom-1", "content": {"value": bottom}})
    body = {"data": {"bookmark_collection_timeline": {"timeline": {"instructions": [{"entries": entries}]}}}}
    return {"url": f"https://x.com/i/api/graphql/h/BookmarkFolderTimeline?variables={quote(json.dumps(variables))}&features=%7B%7D",
            "status": status, "body": json.dumps(body)}


def scenario():
    video = {"type": "video", "media_url_https": "https://pbs.twimg.com/thumb.jpg", "video_info": {"variants": [
        {"content_type": "video/mp4", "bitrate": 100, "url": "https://video.twimg.com/low.mp4"},
        {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/list.m3u8"},
        {"content_type": "video/mp4", "bitrate": 900, "url": "https://video.twimg.com/high.mp4"}]}}
    page1 = [
        item("103", {"__typename": "TweetWithVisibilityResults", "tweet": tweet(
            "103", "alice", "Mon Oct 12 12:00:00 +0000 2026", "Q&amp;A on evals https://t.co/a https://t.co/m",
            urls=[("https://t.co/a", "https://example.org/paper")],
            media=[{"tco": "https://t.co/m", "media": video}], card="https://t.co/a")}),
        item("102", tweet("102", "bob", "Thu Oct 01 12:00:00 +0000 2026", "short version",
                          note="the long note text", quoted=tweet("90", "carol", "Wed Sep 30 12:00:00 +0000 2026", "quoted"))),
        item("101", tweet("101", "dave", "Sun Oct 11 12:00:00 +0000 2026", "middle")),
    ]
    page2 = [
        item("100", tweet("100", "erin", "Fri Oct 09 12:00:00 +0000 2026", "older")),
        {"entryId": "tweet-99", "content": {"itemContent": {"tweet_results": {"result": {"__typename": "TweetTombstone"}}}}},
    ]
    focal = tweet("500", "alice", "Fri Oct 09 12:00:00 +0000 2026", "thread start", reply_to="400")
    detail = {"data": {"threaded_conversation_with_injections_v2": {"instructions": [{"entries": [
        item("400", tweet("400", "zed", "Fri Oct 09 11:00:00 +0000 2026", "parent")),
        item("500", focal),
        {"entryId": "conversationthread-501", "content": {"items": [
            {"entryId": "conversationthread-501-tweet-501", "item": {"itemContent": {"tweet_results": {"result":
                tweet("501", "alice", "Fri Oct 09 12:01:00 +0000 2026", "part 2", reply_to="500")}}}},
            {"entryId": "conversationthread-501-tweet-502", "item": {"itemContent": {"tweet_results": {"result":
                tweet("502", "alice", "Fri Oct 09 12:02:00 +0000 2026", "part 3", reply_to="501")}}}},
            {"entryId": "conversationthread-501-cursor-showmore-1", "item": {"itemContent": {"value": "more"}}}]}},
        {"entryId": "conversationthread-700", "content": {"items": [
            {"entryId": "conversationthread-700-tweet-700", "item": {"itemContent": {"tweet_results": {"result":
                tweet("700", "carl", "Fri Oct 09 14:00:00 +0000 2026", "q", reply_to="500")}}}},
            {"entryId": "conversationthread-700-cursor-showmore-2", "item": {"itemContent": {"value": "side"}}}]}},
        {"entryId": "conversationthread-600", "content": {"items": [
            {"entryId": "conversationthread-600-tweet-600", "item": {"itemContent": {"tweet_results": {"result":
                tweet("600", "bob", "Fri Oct 09 13:00:00 +0000 2026", "nice", reply_to="500")}}}},
            {"entryId": "conversationthread-600-tweet-503", "item": {"itemContent": {"tweet_results": {"result":
                tweet("503", "alice", "Fri Oct 09 13:05:00 +0000 2026", "thanks", reply_to="600")}}}}]}},
    ]}]}}}
    revealed = {"data": {"threaded_conversation_with_injections_v2": {"instructions": [{"entries": [
        {"entryId": "conversationthread-501", "content": {"items": [
            {"entryId": "conversationthread-501-tweet-504", "item": {"itemContent": {"tweet_results": {"result":
                tweet("504", "alice", "Fri Oct 09 12:04:00 +0000 2026", "part 4", reply_to="502")}}}}]}},
    ]}]}}}
    detail_url = "https://x.com/i/api/graphql/h/TweetDetail?variables="
    return {
        "path": f"/i/history/bookmarks/{FOLDER}",
        "responses": [
            folder_response(page1, C1),
            folder_response([item("104", tweet("104", "x", "Sun Oct 18 12:00:00 +0000 2026", "newer"))], None, cursor="top"),
            folder_response(page2, C2, cursor=C1),
            folder_response([item("777", tweet("777", "x", "Sun Oct 18 12:00:00 +0000 2026", "refetch"))], C1),
            folder_response([], None, cursor=C1, status=429),
            folder_response([item("888", tweet("888", "y", "Sun Oct 18 12:00:00 +0000 2026", "other"))], None, folder="42"),
            {"url": "https://x.com/i/api/graphql/h/HomeTimeline?variables=%7B%7D", "status": 200, "body": "{}"},
            folder_response([], None, cursor=C2),
            {"url": detail_url + quote(json.dumps({"focalTweetId": "500"})), "status": 200, "body": json.dumps(detail)},
        ],
        "later": [
            {"url": detail_url + quote(json.dumps({"focalTweetId": "500", "cursor": "more"})),
             "status": 200, "body": json.dumps(revealed)},
        ],
    }


def run_cli(*args):
    return subprocess.run([sys.executable, "-I", "-B", str(CLI), *map(str, args)], capture_output=True, text=True)


@unittest.skipUnless(shutil.which("node"), "node is required to run the page helper")
class PageHelperToCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        scenario_path = cls.dir / "scenario.json"
        scenario_path.write_text(json.dumps(scenario()))
        result = subprocess.run(["node", "-e", HARNESS, str(HELPER), str(scenario_path)],
                                capture_output=True, text=True, check=True)
        cls.out = json.loads(result.stdout)
        cls.capture = cls.dir / "capture.json"
        cls.capture.write_text(json.dumps(cls.out["full"]))
        cls.first = cls.dir / "first.json"
        cls.first.write_text(json.dumps(cls.out["first"]))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_folder_pages_follow_the_cursor_chain(self):
        doc = self.out["full"]
        self.assertEqual(doc["folder"]["id"], FOLDER)
        self.assertTrue(doc["complete"])
        self.assertEqual([p["items"] for p in doc["pages"]], [3, 2, 0])
        self.assertEqual(doc["pages"][0]["cursor_time"], "2026-10-10T12:00:00.000Z")
        self.assertEqual(doc["http_errors"], [429])
        self.assertEqual([(r["id"], r["page"], r["pos"]) for r in doc["records"]],
                         [("103", 1, 1), ("102", 1, 2), ("101", 1, 3), ("100", 2, 1), ("99", 2, 2)])

    def test_records_carry_readable_text_links_and_media(self):
        records = {r["id"]: r for r in self.out["full"]["records"]}
        first = records["103"]
        self.assertEqual(first["text"], "Q&A on evals https://example.org/paper")
        self.assertEqual(first["links"], ["https://example.org/paper"])
        self.assertEqual(first["card_url"], "https://example.org/paper")
        self.assertEqual(first["media"][0]["video"], "https://video.twimg.com/high.mp4")
        self.assertEqual(first["url"], "https://x.com/alice/status/103")
        self.assertEqual(records["102"]["text"], "the long note text")
        self.assertEqual(records["102"]["quoted"]["id"], "90")
        self.assertEqual(records["99"], {"page": 2, "pos": 2, "id": "99", "url": "https://x.com/i/status/99",
                                         "unavailable": "TweetTombstone"})

    def test_thread_keeps_the_author_chain_and_parent_context(self):
        thread = self.out["thread"]
        self.assertEqual([p["id"] for p in thread["context"]], ["400"])
        self.assertEqual([p["id"] for p in thread["self_thread"]], ["500", "501", "502"])
        self.assertEqual(thread["other_replies"], 3)
        self.assertTrue(thread["self_thread_truncated"])
        revealed = self.out["revealed"]
        self.assertEqual([p["id"] for p in revealed["self_thread"]], ["500", "501", "502", "504"])
        self.assertFalse(revealed["self_thread_truncated"])

    def test_window_status_uses_cursor_and_publish_bounds(self):
        rows = [json.loads(line) for line in run_cli(
            "list", self.capture, "--since", "2026-10-11", "--tz", "UTC", "--format", "jsonl").stdout.splitlines()]
        status = {r["id"]: r["window"] for r in rows}
        # 102 was published Oct 1 but sits above 101 (published Oct 11), so it was saved after Oct 11.
        self.assertEqual(status, {"103": "in", "102": "in", "101": "in", "100": "out", "99": "out"})
        rows = [json.loads(line) for line in run_cli(
            "list", self.capture, "--since", "2026-10-10", "--tz", "UTC", "--format", "jsonl").stdout.splitlines()]
        self.assertEqual({r["id"]: r["window"] for r in rows}["100"], "boundary")
        self.assertEqual(rows[3]["added_after"], "2026-10-09T12:00:00Z")
        self.assertEqual(rows[3]["added_before"], "2026-10-10T12:00:00Z")

    def test_summary_flags_a_window_the_capture_does_not_reach(self):
        self.assertEqual(run_cli("summary", self.first, "--since", "2026-10-11", "--tz", "UTC").returncode, 0)
        uncovered = run_cli("summary", self.first, "--since", "2026-10-01", "--tz", "UTC")
        self.assertEqual(uncovered.returncode, 2)
        self.assertIn("NOT COVERED", uncovered.stdout)
        self.assertEqual(run_cli("summary", self.capture, "--since", "2020-01-01").returncode, 0)

    def test_diff_reads_capture_snapshot_and_intake_formats(self):
        priors = {
            "capture": {"schema": "x-bookmark-folder-capture/1", "records": [{"id": "103"}, {"id": "55"}]},
            "snapshot": {"posts": [{"post_id": "103"}, {"post_id": "55"}]},
            "intake": {"bookmarks": [{"post_id": "103", "first_observed_at": "2026-09-30T23:11:05Z"}, {"post_id": "55"}]},
        }
        for name, prior in priors.items():
            with self.subTest(prior=name):
                path = self.dir / f"prior-{name}.json"
                path.write_text(json.dumps(prior))
                text = run_cli("diff", self.capture, path).stdout
                self.assertIn("4 new, 1 absent", text)
                self.assertIn("absent 55", text)
        rows = {r["id"]: r for r in map(json.loads, run_cli(
            "diff", self.capture, self.dir / "prior-intake.json", "--format", "jsonl").stdout.splitlines())}
        self.assertEqual(rows["103"]["first_observed_at"], "2026-09-30T23:11:05Z")
        self.assertEqual(rows["101"]["status"], "new")
        bad = self.dir / "bad.json"
        bad.write_text("{}")
        self.assertEqual(run_cli("diff", self.capture, bad).returncode, 1)


def tiny_pdf(title: str) -> bytes:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>", f"<< /Title ({title}) >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


ROUTES = {
    "/paper.pdf": ("application/pdf", tiny_pdf("First Paper"), 0),
    "/other.pdf": ("application/pdf", tiny_pdf("Second Paper"), 0),
    "/login": ("text/html", b"<!DOCTYPE html><html><body>Sign in</body></html>", 0),
    "/short.pdf": ("application/pdf", tiny_pdf("Cut")[:120], 500),
    "/noeof.pdf": ("application/octet-stream", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", 0),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        content_type, body, extra = ROUTES[self.path]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body) + extra))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, *args):
        pass


class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dest = Path(tmp.name) / "papers"
        self.manifest = Path(tmp.name) / "manifest.jsonl"

    def fetch(self, route, *extra):
        return run_cli("fetch", self.base + route, "--dest", self.dest, "--manifest", self.manifest, *extra)

    def test_saves_once_reuses_identical_bytes_and_never_overwrites(self):
        saved = self.fetch("/paper.pdf", "--name", "first-paper", "--ref", "https://x.com/a/status/1")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        row = json.loads(saved.stdout)
        target = self.dest / "first-paper.pdf"
        self.assertEqual((row["status"], row["path"], row["refs"]), ("saved", str(target), ["https://x.com/a/status/1"]))
        self.assertEqual(row["sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
        if shutil.which("pdfinfo"):
            self.assertEqual((row["checks"]["pages"], row["checks"]["title"]), (1, "First Paper"))
        self.assertEqual(json.loads(self.fetch("/paper.pdf", "--name", "first-paper").stdout)["status"], "reused")
        clash = self.fetch("/other.pdf", "--name", "first-paper")
        self.assertEqual(clash.returncode, 1)
        self.assertIn("different content", clash.stderr)
        self.assertEqual(target.read_bytes(), tiny_pdf("First Paper"))
        self.assertEqual(len(self.manifest.read_text().splitlines()), 2)

    def test_rejects_html_truncated_and_unterminated_transfers(self):
        for route, kind, message in [("/login", "pdf", "HTML"), ("/short.pdf", "auto", "truncated"),
                                     ("/noeof.pdf", "pdf", "%%EOF")]:
            with self.subTest(route=route):
                result = self.fetch(route, "--kind", kind)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(message, result.stderr)
        self.assertFalse(self.dest.exists() and any(self.dest.iterdir()))
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
