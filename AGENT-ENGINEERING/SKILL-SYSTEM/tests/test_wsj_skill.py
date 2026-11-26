from __future__ import annotations

from pathlib import Path
import base64
import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import unittest
import argparse
import importlib.util
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WSJ = ROOT / "skills" / "wsj"
TEXT_FILES = (
    WSJ / "SKILL.md",
    WSJ / "agents" / "openai.yaml",
    WSJ / "references" / "applescript-fallback.md",
    WSJ / "references" / "chrome-plugin-workflow.md",
    WSJ / "references" / "claude-in-chrome-workflow.md",
    WSJ / "references" / "research-playbook.md",
    WSJ / "references" / "site-map.md",
)


class WsjSkillTextTests(unittest.TestCase):
    def test_text_files_exist_and_are_nonempty(self) -> None:
        for path in TEXT_FILES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
                self.assertTrue(path.read_text().strip())


class StoryClassificationTests(unittest.TestCase):
    def test_frontpage_and_latest_classify_url_and_native_flags_consistently(self) -> None:
        spec = importlib.util.spec_from_file_location("wsj_research", WSJ / "scripts" / "wsj_research.py")
        wsj = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wsj)
        cases = [("https://www.wsj.com/opinion/story", False, "Business", True),
                 ("https://www.wsj.com/%4Fpinion/missing-flag", None, "Business", True),
                 ("https://www.wsj.com/news/story", True, "Business", True),
                 ("https://www.wsj.com/news/editorial", False, "Opinion / Review", True),
                 ("https://www.wsj.com/business/story?opinion=yes", False, "Business", False),
                 ("https://www.wsj.com/business/opinionated-company", False, "Business", False)]
        for command in (wsj.command_frontpage, wsj.command_latest):
            for exclude in (True, False):
                data = {"stories": [{"url": url, **({"is_opinion": flag} if flag is not None else {}), "section": section,
                         "headline": "An opinion about ordinary reporting", "is_video": False}
                         for url, flag, section, _ in cases]}
                tab = mock.Mock(transport="claude-in-chrome")
                with mock.patch.object(wsj, "_connect", return_value=contextlib.nullcontext(tab)), \
                        mock.patch.object(wsj, "_require_login"), \
                        mock.patch.object(wsj, "_execute_json", return_value=data), \
                        mock.patch.object(wsj, "_print_json") as output:
                    command(argparse.Namespace(exclude_opinion=exclude, include_extras=False, exclude_video=False, max=10,
                                               transport="auto"))
                self.assertEqual(output.call_args.args[0]["transport"], "claude-in-chrome")
                stories = output.call_args.args[0]["stories"]
                self.assertEqual([s["url"] for s in stories], [url for url, _, _, opinion in cases if not (exclude and opinion)])
                if not exclude:
                    self.assertEqual([s["is_opinion"] for s in stories], [opinion for _, _, _, opinion in cases])


class NavigationTests(unittest.TestCase):
    def test_navigation_waits_for_a_new_document_not_the_old_page_s_data(self) -> None:
        # 10-05: a homepage scan from an article tab read the article; __NEXT_DATA__ was already on it
        spec = importlib.util.spec_from_file_location("wsj_research", WSJ / "scripts" / "wsj_research.py")
        wsj = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wsj)
        with mock.patch.object(wsj, "_run_applescript", return_value="ready|||WSJ-RESEARCH|||https://www.wsj.com/") as run, \
                mock.patch.object(wsj.time, "sleep"):
            wsj._navigate({"window_id": 1, "tab_id": 2}, "https://www.wsj.com/")
        script = run.call_args.args[0]
        self.assertLess(script.index("__wsjResearchLeaving = true"), script.index("set URL of targetTab"))
        self.assertIn("!window.__wsjResearchLeaving ? 'ready'", script)



def load_wsj():
    spec = importlib.util.spec_from_file_location("wsj_research", WSJ / "scripts" / "wsj_research.py")
    wsj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wsj)
    return wsj


class TargetTests(unittest.TestCase):
    # Mo§7, TM (10-20): every tab of every window was walked to validate the saved tab while Claude in Chrome opened
    # and closed tabs, and the walk failed (-1719); the newest 15 minutes of WSJ went unscanned.
    def test_a_saved_tab_is_checked_by_its_ids_without_walking_every_tab(self) -> None:
        wsj = load_wsj()
        state = {"window_id": 1620, "tab_id": 99, "profile_email": wsj.PROFILE_EMAIL, "profile_directory": "Default",
                 "owned": True}
        scripts = []

        def run(script: str) -> str:
            scripts.append(script)
            return "yes"
        with mock.patch.object(wsj, "_resolve_profile_directory", return_value="Default"), \
                mock.patch.object(wsj, "_load_state", return_value=state), \
                mock.patch.object(wsj, "_run_applescript", side_effect=run):
            self.assertEqual(wsj._target(), state)
        self.assertEqual(len(scripts), 1)
        self.assertIn("first window whose id is 1620", scripts[0])
        self.assertIn("whose id is 99", scripts[0])

    # 11-24: the fallback adopted and navigated a WSJ tab the user had open, and added a chrome://version tab to the
    # user's window to check its profile.
    def test_a_saved_tab_the_helper_did_not_open_is_not_reused(self) -> None:
        wsj = load_wsj()
        adopted = {"window_id": 1620, "tab_id": 99, "profile_email": wsj.PROFILE_EMAIL, "profile_directory": "Default"}
        opened = {**adopted, "window_id": 7, "tab_id": 8, "owned": True}
        with mock.patch.object(wsj, "_resolve_profile_directory", return_value="Default"), \
                mock.patch.object(wsj, "_load_state", return_value=adopted), \
                mock.patch.object(wsj, "_run_applescript") as run, \
                mock.patch.object(wsj, "_open_profile_window", return_value=opened) as open_window, \
                mock.patch.object(wsj, "_save_state") as save, mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(wsj._target(), opened)
        run.assert_not_called()
        open_window.assert_called_once_with("Default")
        save.assert_called_once_with(opened)

    def test_the_helper_window_is_made_in_the_running_chrome_and_its_profile_is_checked_there(self) -> None:
        # `open -na` started a second Chrome process for a moment, and AppleScript failed with -609 (11-24).
        wsj = load_wsj()
        scripts = []

        def run(script: str) -> str:
            scripts.append(script)
            return "41" if "make new window" in script else "42" if "active tab" in script else ""
        for found, expected in (("Default", {"window_id": 41, "tab_id": 42}), ("Profile 10", None)):
            scripts.clear()
            with mock.patch.object(wsj, "_run_applescript", side_effect=run), \
                    mock.patch.object(wsj, "_window_profile_directory", return_value=found) as probe, \
                    mock.patch.object(wsj, "_returning_front_app", return_value=contextlib.nullcontext()), \
                    mock.patch.object(wsj.subprocess, "run") as shell:
                if expected:
                    target = wsj._open_profile_window("Default")
                    self.assertEqual({k: target[k] for k in ("window_id", "tab_id")}, expected)
                    self.assertIs(target["owned"], True)
                else:
                    with self.assertRaises(wsj.WsjError) as raised:
                        wsj._open_profile_window("Default")
                    self.assertEqual(raised.exception.exit_code, wsj.EXIT_BROWSER_TIMEOUT)
                    self.assertTrue(any("close (first window whose id is 41)" in script for script in scripts))
            probe.assert_called_once_with(41)
            shell.assert_not_called()


class FrontAppTests(unittest.TestCase):
    GHOSTTY, CHROME = "com.mitchellh.ghostty", "com.google.Chrome"

    def check(self, fronts: list[str | None], *, fail: bool = False) -> list[list[str]]:
        """The commands run when the front app reads FRONTS, one per look, and then stays at the last one."""
        wsj = load_wsj()
        clock = [0.0]
        looks = iter(fronts)
        last = [fronts[-1]]

        def front() -> str | None:
            last[0] = next(looks, last[0])
            return last[0]

        def sleep(seconds: float) -> None:
            clock[0] += seconds
        with mock.patch.object(wsj, "_front_bundle_id", side_effect=front), \
                mock.patch.object(wsj.subprocess, "run") as run, \
                mock.patch.object(wsj.time, "sleep", side_effect=sleep), \
                mock.patch.object(wsj.time, "monotonic", side_effect=lambda: clock[0]):
            with contextlib.suppress(RuntimeError), wsj._returning_front_app():
                if fail:
                    raise RuntimeError
        return [call.args[0] for call in run.call_args_list]

    def test_the_front_goes_back_only_when_chrome_took_it_from_another_app(self) -> None:
        g, c = self.GHOSTTY, self.CHROME
        self.assertEqual(self.check([g, g, c, c, g]), [["open", "-b", g]])
        self.assertEqual(self.check([c, c]), [])
        self.assertEqual(self.check([None, c]), [])
        self.assertEqual(self.check([g, "com.apple.Safari"]), [])
        self.assertEqual(self.check([g, g]), [])  # Chrome never came forward within the watch
        self.assertEqual(self.check([g, c, c, g], fail=True), [["open", "-b", g]])
        self.assertEqual(self.check([g, g], fail=True), [])

    def test_chrome_taking_the_front_again_is_answered_until_the_limit(self) -> None:
        # 11-24: after `open -b` handed the front back, Chrome took it again 0.2 s later.
        g, c = self.GHOSTTY, self.CHROME
        self.assertEqual(self.check([g, c, c, g, c, c, g]), [["open", "-b", g]] * 2)
        self.assertEqual(self.check([g, c, c]), [["open", "-b", g]] * 3)
        self.assertEqual(self.check([g, c, g]), [])  # Chrome let go while settling


def encode_like_the_page(value: str, size: int, per_call: int) -> list[dict]:
    """What CIC_RESULT_JS and __wsjResearchSlice return, call by call."""
    encoded = base64.b64encode(gzip.compress(value.encode("utf-8"))).decode("ascii")
    pieces = ["~" + encoded[i:i + size] for i in range(0, len(encoded), size)]
    return [{"total": len(encoded), "parts": pieces[i:i + per_call]} for i in range(0, len(pieces), per_call)] or \
        [{"total": 0, "parts": []}]


class FakeServer:
    """Answers Claude in Chrome tool calls from a script of (name -> text or callable)."""

    def __init__(self, answers: dict):
        self.answers, self.calls, self.closed = answers, [], False

    def tool(self, name: str, arguments: dict, **_: object) -> str:
        self.calls.append((name, arguments))
        answer = self.answers[name]
        return answer(arguments) if callable(answer) else answer

    def close(self) -> None:
        self.closed = True


class ClaudeInChromeResultTests(unittest.TestCase):
    VALUE = json.dumps({"authors": ["A Writer"], "text": "P/E = 20; a=b&c=d U.S.A \u2014 \u201cquoted\u201d"})

    def test_a_result_survives_the_part_size_and_per_call_limits(self) -> None:
        wsj = load_wsj()
        value = self.VALUE + "".join(hashlib.sha256(str(i).encode()).hexdigest() for i in range(2000))
        pages = encode_like_the_page(value, wsj.CIC_PART_SIZE, wsj.CIC_PARTS_PER_CALL)
        self.assertGreater(len(pages), 1)
        offsets = []

        def javascript(arguments: dict) -> str:
            text = arguments["text"]
            if text.startswith("await (async"):
                self.assertIn("parts.length < 45", text)
                return json.dumps(pages[0])
            offset = int(re.fullmatch(r"window\.__wsjResearchSlice\((\d+)\)", text).group(1))
            offsets.append(offset)
            index = offset // (wsj.CIC_PART_SIZE * wsj.CIC_PARTS_PER_CALL)
            return json.dumps(pages[index])
        tab = wsj.ClaudeInChromeTab(FakeServer({"javascript_tool": javascript}), 5, keep=True)
        self.assertEqual(tab.evaluate("(() => 'x')()"), value)
        self.assertEqual(offsets, [wsj.CIC_PART_SIZE * wsj.CIC_PARTS_PER_CALL * i for i in range(1, len(pages))])

    def test_a_result_the_extension_rewrote_fails_loudly(self) -> None:
        wsj = load_wsj()
        page = encode_like_the_page(self.VALUE, wsj.CIC_PART_SIZE, wsj.CIC_PARTS_PER_CALL)[0]
        redacted = {**page, "parts": [page["parts"][0][:40] + "[value redacted]" + page["parts"][0][56:]]}
        blocked = {**page, "parts": ["[BLOCKED: Base64 encoded data]"]}
        short = {**page, "total": page["total"] + 4}
        for altered in (redacted, blocked, short):
            with self.subTest(altered=str(altered)[:60]), self.assertRaises(wsj.WsjError):
                wsj._cic_decode(*wsj._cic_parts(altered))
        self.assertEqual(wsj._cic_decode(*wsj._cic_parts(page)), self.VALUE)


class ClaudeInChromeTabTests(unittest.TestCase):
    CONTEXT = json.dumps({"availableTabs": [{"tabId": 11, "url": "chrome://newtab/"},
                                            {"tabId": 12, "url": "https://www.wsj.com/"}], "tabGroupId": 3})

    def claim(self, answers: dict, saved: dict) -> tuple[tuple[int, bool], FakeServer, mock.Mock]:
        wsj = load_wsj()
        server = FakeServer(answers)
        with mock.patch.object(wsj, "_load_json", return_value=saved), \
                mock.patch.object(wsj, "_save_json") as save, \
                mock.patch.object(wsj, "_returning_front_app", return_value=contextlib.nullcontext()), \
                mock.patch("sys.stderr", io.StringIO()):
            return wsj._claim_cic_tab(server), server, save

    def test_the_saved_anchor_tab_is_reused_and_kept(self) -> None:
        claimed, server, save = self.claim({"tabs_context_mcp": self.CONTEXT}, {"tab_id": 12})
        self.assertEqual(claimed, (12, True))
        self.assertEqual([name for name, _ in server.calls], ["tabs_context_mcp"])
        save.assert_not_called()

    def test_in_a_group_someone_else_made_the_helper_adds_a_tab_for_the_run(self) -> None:
        claimed, server, save = self.claim({"tabs_context_mcp": self.CONTEXT, "tabs_create_mcp":
                                            "Created new tab. Tab ID: 13"}, {"tab_id": 99})
        self.assertEqual(claimed, (13, False))
        save.assert_not_called()

    def test_without_a_group_the_helper_creates_it_and_keeps_its_anchor_tab(self) -> None:
        def context(arguments: dict) -> str:
            return json.dumps({"availableTabs": [{"tabId": 21}]}) if arguments.get("createIfEmpty") else \
                "No MCP tab groups found. Use createIfEmpty: true to create a group."
        claimed, server, save = self.claim({"tabs_context_mcp": context}, {})
        self.assertEqual(claimed, (21, True))
        self.assertEqual(server.calls[-1], ("tabs_context_mcp", {"createIfEmpty": True}))
        save.assert_called_once()
        self.assertEqual(save.call_args.args[1], {"tab_id": 21})

    def test_only_a_tab_added_for_the_run_is_closed(self) -> None:
        wsj = load_wsj()
        for keep, closes in ((True, []), (False, [("tabs_close_mcp", {"tabId": 13})])):
            server = FakeServer({"tabs_close_mcp": "Closed tab 13."})
            wsj.ClaudeInChromeTab(server, 13, keep=keep).close()
            self.assertEqual(server.calls, closes)
            self.assertTrue(server.closed)


class TransportChoiceTests(unittest.TestCase):
    def test_auto_falls_back_to_applescript_only_when_claude_in_chrome_does_not_connect(self) -> None:
        wsj = load_wsj()
        down = wsj.ClaudeInChromeUnavailable("Browser extension is not connected")
        target = {"window_id": 1, "tab_id": 2, "profile_directory": "Default"}
        with mock.patch.object(wsj.ClaudeInChromeTab, "open", side_effect=down), \
                mock.patch.object(wsj, "_target", return_value=target), \
                mock.patch("sys.stderr", io.StringIO()) as stderr:
            with wsj._connect("auto") as tab:
                self.assertEqual(tab.transport, "applescript")
            self.assertIn("not connected", stderr.getvalue())
            with self.assertRaises(wsj.ClaudeInChromeUnavailable), wsj._connect("claude-in-chrome"):
                pass
        cic = mock.Mock(transport="claude-in-chrome")
        with mock.patch.object(wsj.ClaudeInChromeTab, "open", return_value=cic), \
                mock.patch.object(wsj, "_target") as applescript:
            with wsj._connect("auto") as tab:
                self.assertIs(tab, cic)
        applescript.assert_not_called()
        cic.close.assert_called_once()

    def test_connecting_is_retried_once_on_a_fresh_server(self) -> None:
        wsj = load_wsj()
        servers = []

        def server() -> mock.Mock:
            fake = mock.Mock()
            if not servers:
                fake.request.side_effect = wsj.WsjError("did not answer initialize within 20s.", 12)
            servers.append(fake)
            return fake
        with mock.patch.object(wsj, "_McpServer", side_effect=server), \
                mock.patch.object(wsj, "_claim_cic_tab", return_value=(7, True)):
            tab = wsj.ClaudeInChromeTab.open()
        self.assertEqual((tab.tab_id, len(servers)), (7, 2))
        servers[0].close.assert_called_once()
        with mock.patch.object(wsj, "_McpServer", side_effect=wsj.ClaudeInChromeUnavailable("cannot start")), \
                self.assertRaisesRegex(wsj.ClaudeInChromeUnavailable, "cannot start Retried: cannot start"):
            wsj.ClaudeInChromeTab.open()


FAKE_MCP_SERVER = """#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    if message["method"] == "exit-now":
        sys.exit(0)
    print("not json", flush=True)
    if message["method"] == "env":
        import os
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"home": os.environ["HOME"],
              "key": "ANTHROPIC_API_KEY" in os.environ}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}), flush=True)
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"] + 1000, "result": {}}), flush=True)
    if message["method"] == "silent":
        continue
    text = {"content": [{"type": "text", "text": "<system-reminder>for models</system-reminder>"},
                        {"type": "text", "text": "Navigated to " + str(message["params"].get("arguments", {}).get("url"))}],
            "isError": message["params"].get("name") == "broken"}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": text}), flush=True)
"""


class McpFramingTests(unittest.TestCase):
    def test_requests_match_their_answers_through_noise_timeouts_and_exit(self) -> None:
        wsj = load_wsj()
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "claude"
            binary.write_text(FAKE_MCP_SERVER)
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
            with mock.patch.object(wsj, "CLAUDE_BINARY", binary), mock.patch.object(wsj, "REAL_HOME", Path(directory)), \
                    mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-not-real"}):
                server = wsj._McpServer()
                try:
                    self.assertEqual(server.request("env", {}, 10), {"home": directory, "key": False})
                    self.assertEqual(server.tool("navigate", {"url": "https://www.wsj.com/"}, timeout=10),
                                     "Navigated to https://www.wsj.com/")
                    with self.assertRaisesRegex(wsj.WsjError, "broken"):
                        server.tool("broken", {}, timeout=10)
                    with self.assertRaisesRegex(wsj.WsjError, "did not answer silent"):
                        server.request("silent", {}, 0.5)
                    with self.assertRaisesRegex(wsj.WsjError, "exited"):
                        server.request("exit-now", {}, 10)
                finally:
                    server.close()
        self.assertTrue(os.environ.get("HOME"))  # the test never changed this process's HOME


if __name__ == "__main__":
    unittest.main()
