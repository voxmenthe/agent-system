from __future__ import annotations

from pathlib import Path
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
                with mock.patch.object(wsj, "_target", return_value={"window_id": 1, "tab_id": 1}), \
                        mock.patch.object(wsj, "_navigate"), mock.patch.object(wsj, "_require_login"), \
                        mock.patch.object(wsj, "_execute_json", return_value=data), \
                        mock.patch.object(wsj, "_print_json") as output:
                    command(argparse.Namespace(exclude_opinion=exclude, include_extras=False, exclude_video=False, max=10))
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


STALE_INDEX = ("Chrome automation failed: execution error: Google Chrome got an error: Can't get item 43 of every "
               "tab of window id 1620. (-1719)")


class TargetTests(unittest.TestCase):
    # Mo§7, TM (10-20): every tab of every window was walked to validate the saved tab while Claude in Chrome opened
    # and closed tabs, and the walk failed (-1719); the newest 15 minutes of WSJ went unscanned.
    def test_a_saved_tab_is_checked_by_its_ids_without_walking_every_tab(self) -> None:
        wsj = load_wsj()
        state = {"window_id": 1620, "tab_id": 99, "profile_email": wsj.PROFILE_EMAIL, "profile_directory": "Default"}
        scripts = []

        def run(script: str) -> str:
            scripts.append(script)
            if "repeat with browserTab" in script:
                raise wsj.WsjError(STALE_INDEX)
            return "yes"
        with mock.patch.object(wsj, "_resolve_profile_directory", return_value="Default"), \
                mock.patch.object(wsj, "_load_state", return_value=state), \
                mock.patch.object(wsj, "_run_applescript", side_effect=run):
            self.assertEqual(wsj._target(), state)
        self.assertEqual(len(scripts), 1)
        self.assertIn("first window whose id is 1620", scripts[0])
        self.assertIn("whose id is 99", scripts[0])

    def test_the_tab_walk_is_retried_once_when_a_tab_closes_mid_walk(self) -> None:
        wsj = load_wsj()
        listing = "1620|||WSJ-RESEARCH|||99|||WSJ-RESEARCH|||https://www.wsj.com/\n"
        for drops, expected in ((1, [{"window_id": 1620, "tab_id": 99, "url": "https://www.wsj.com/"}]), (2, None)):
            left = [drops]

            def run(script: str) -> str:
                if left[0]:
                    left[0] -= 1
                    raise wsj.WsjError(STALE_INDEX)
                return listing
            with mock.patch.object(wsj, "_run_applescript", side_effect=run), mock.patch.object(wsj.time, "sleep"):
                if expected is None:
                    with self.assertRaisesRegex(wsj.WsjError, "-1719"):
                        wsj._all_tabs()
                else:
                    self.assertEqual(wsj._all_tabs(), expected)


if __name__ == "__main__":
    unittest.main()
