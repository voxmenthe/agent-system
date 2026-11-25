"""Source contracts and the real am shell boundary, without network/inference."""

import copy
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures/agent-models"
sys.path.insert(0, str(SOURCE))
import agent_model_sources as sources
import agent_models as models
from agent_model_picker import detail

BASH = shutil.which("bash")
NOW = datetime(2026, 10, 16, tzinfo=UTC).timestamp()


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def offer_html(rows: list[dict]) -> str:
    payload = json.dumps([1, "a:" + json.dumps({"rows": rows}) + "\n"])
    return f"<script>self.__next_f.push({payload})</script>"


def curated_offers() -> dict:
    return {
        "schema_version": 1,
        "offers": [
            {
                "id": "future-intro",
                "models": ["devin:future-family-high"],
                "discounts": {"Self-serve": 75, "Legacy credits": 50},
                "starts": "2020-01-01",
                "through": "2099-12-31",
                "checked_at": "2026-10-16",
                "source": "https://example.com/official-pricing",
                "condition": "Advertised terms; account eligibility not verified",
            }
        ],
    }


class SourceContractTests(unittest.TestCase):
    def test_curated_offers_annotate_exact_live_ids_without_changing_prices(
        self,
    ) -> None:
        rows = sources.parse_devin(fixture("devin"))
        original = [m.record() for m in rows]
        payload = curated_offers()
        payload["offers"][0]["models"] += [
            "devin:missing-native-model",
            "oc:opencode/future-family-high",
        ]
        sources.annotate_curated_offers(rows, payload, NOW)
        self.assertEqual(len(original), len(rows))
        for before, model in zip(original, rows):
            self.assertEqual(before["pricing"], model.pricing)
            self.assertEqual(before["details"]["cost_tier"], model.details["cost_tier"])
            self.assertEqual(
                before["details"]["cost_summary"], model.details["cost_summary"]
            )
            self.assertEqual(
                model.native_id == "future-family-high", "deal" in model.badges
            )
        target = next(m for m in rows if m.deal)
        self.assertEqual(
            {"Self-serve": 75, "Legacy credits": 50},
            target.details["offer"]["discounts"],
        )
        self.assertIn("eligibility not verified", detail(target))

    def test_curated_dates_are_inclusive_utc_and_never_stack(self) -> None:
        payload = curated_offers()
        first = payload["offers"][0]
        first.update(starts="2026-10-13", through="2026-10-27")
        following = {
            **first,
            "id": "intro-only",
            "starts": "2026-10-28",
            "through": "2026-12-01",
            "discounts": {"Self-serve": 50},
        }
        payload["offers"].append(following)
        for stamp, expected in (
            ("2026-10-12T23:59:59+00:00", None),
            ("2026-10-13T00:00:00+00:00", 75),
            ("2026-10-27T23:59:59+00:00", 75),
            ("2026-10-28T00:00:00+00:00", 50),
            ("2026-12-02T00:00:00+00:00", None),
        ):
            with self.subTest(stamp=stamp):
                rows = sources.parse_devin(fixture("devin"))
                sources.annotate_curated_offers(
                    rows, payload, datetime.fromisoformat(stamp).timestamp()
                )
                target = next(m for m in rows if m.native_id == "future-family-high")
                self.assertEqual(expected is not None, "deal" in target.badges)
                if expected is not None:
                    self.assertEqual(
                        expected, target.details["offer"]["discounts"]["Self-serve"]
                    )

    def test_curated_invalid_or_ambiguous_terms_are_rejected(self) -> None:
        for change in (
            {"through": "sometime"},
            {"starts": "2100-01-01"},
            {"models": ["future-family-high"]},
            {"models": []},
            {"discounts": {"Self-serve": True}},
            {"discounts": {"Self-serve": 101}},
            {"discounts": {}},
            {"source": ""},
            {"checked_at": "unknown"},
        ):
            with self.subTest(change=change):
                payload = curated_offers()
                payload["offers"][0].update(change)
                with self.assertRaises(sources.SourceError):
                    sources.annotate_curated_offers([], payload, NOW)
        for payload in (
            {**curated_offers(), "schema_version": 2},
            {**curated_offers(), "offers": curated_offers()["offers"] * 2},
            {
                "schema_version": 1,
                "offers": [
                    curated_offers()["offers"][0],
                    {**curated_offers()["offers"][0], "id": "overlapping"},
                ],
            },
        ):
            with self.subTest(payload=payload), self.assertRaises(sources.SourceError):
                sources.annotate_curated_offers([], payload, NOW)

    def test_command_code_rich_fields_hidden_rows_null_efforts_and_price_truth(
        self,
    ) -> None:
        rows = sources.parse_cmd(fixture("cmd"))
        by_id = {m.native_id: m for m in rows}
        self.assertNotIn("legacy/free", by_id)
        free = by_id["stealth/cat-jam:free"]
        self.assertEqual(
            "stealth reasoning model for coding and agentic work", free.description
        )
        self.assertEqual(["low", "high", "max"], free.efforts)
        self.assertEqual(1048576, free.context)
        self.assertEqual("individual-go", free.details["minimum_plan"])
        self.assertEqual("unknown", free.eligibility)
        self.assertEqual(["free", "stealth"], free.badges)
        self.assertEqual([], by_id["xiaomi/mimo-v2.5-pro"].efforts)
        for native in ("vendor/paid", "vendor/unknown", "vendor/cache-cost"):
            self.assertNotIn("free", by_id[native].badges)

    def test_schema_and_required_identity_fail_instead_of_guessing(self) -> None:
        for change in (
            {"schemaVersion": 2},
            {"data": None},
            {"data": [{"name": "No ID"}]},
            {"data": [{"id": "bad\n-id", "name": "Bad"}]},
        ):
            with self.subTest(change=change), self.assertRaises(sources.SourceError):
                sources.parse_cmd({**fixture("cmd"), **change})

    def test_opencode_whitelist_capabilities_tiers_and_secrets(self) -> None:
        rows = sources.parse_oc(fixture("oc"), "/fixture-project")
        self.assertEqual(
            {"opencode", "opencode-go"}, {m.native_id.split("/")[0] for m in rows}
        )
        by_id = {m.native_id: m for m in rows}
        self.assertNotIn("opencode/disabled", by_id)
        self.assertNotIn("opencode/decision-only", by_id)
        self.assertIn("free", by_id["opencode/future-coding-free"].badges)
        self.assertNotIn("free", by_id["opencode-go/future-coding-free"].badges)
        self.assertNotIn("free", by_id["opencode/tiered"].badges)
        serialized = json.dumps([m.record() for m in rows])
        for secret in ("DO_NOT_LEAK", "apiKey", "settings", "headers", "Authorization"):
            self.assertNotIn(secret, serialized)
        with self.assertRaises(sources.SourceError):
            sources.parse_oc(fixture("oc"), "/wrong-project")

    def test_native_new_and_beta_are_separate_and_uids_are_not_synthesized(
        self,
    ) -> None:
        rows = sources.parse_devin(fixture("devin"))
        by_id = {m.native_id: m for m in rows}
        self.assertIn("free", by_id["swe-2-max"].badges)
        self.assertIn("new", by_id["future-family-high"].badges)
        self.assertNotIn("new", by_id["future-family-beta"].badges)
        self.assertIn("fusion-future-high-sidekick-swe-2-high", by_id)

    def test_offer_join_uses_model_id_and_preserves_conditions_and_unknown_references(
        self,
    ) -> None:
        rows = sources.parse_cmd(fixture("cmd"))
        sources.annotate_cmd_offers(
            rows, (FIXTURES / "cmd-pricing.html").read_text(), NOW
        )
        by_id = {m.native_id: m for m in rows}
        free = by_id["stealth/cat-jam:free"]
        self.assertEqual("while capacity lasts", free.details["offer"]["condition"])
        self.assertNotIn("deal", by_id["vendor/paid"].badges)
        self.assertNotIn("free", by_id["vendor/paid"].badges)
        deal = by_id["xiaomi/mimo-v2.5-pro"]
        self.assertIn("deal", deal.badges)
        self.assertIsNone(deal.details["published_tiers"][1]["listRates"])
        self.assertEqual("advertised token discount", deal.details["offer"]["kind"])

    def test_expired_unknown_conflicting_and_boosted_offers(self) -> None:
        for expires, rates, expected in (
            ("2020-01-01", {"input": 0, "output": 0}, "expired"),
            ("not-a-date", {"input": 0, "output": 0}, "unknown expiry"),
            (None, {"input": 1, "output": 0}, "conflicting free terms"),
        ):
            row = {
                "id": "unknown",
                "name": "Unknown Price",
                "availability": {},
                "tiers": [{"rates": rates}],
                "deal": {
                    "id": "promo-is-not-a-model",
                    "discountPercent": 100,
                    "free": True,
                    "expires": expires,
                },
            }
            catalog = sources.parse_cmd(fixture("cmd"))
            sources.annotate_cmd_offers(catalog, offer_html([row]), NOW)
            target = next(m for m in catalog if m.native_id == "vendor/unknown")
            self.assertEqual(expected, target.details["offer"]["status"])
            self.assertNotIn("free", target.badges)
            self.assertNotIn("deal", target.badges)
        row["deal"] = {"id": "unknown-2x-usage", "discountPercent": 50, "free": False}
        sources.annotate_cmd_offers(catalog, offer_html([row]), NOW)
        self.assertEqual("boosted usage allowance", target.details["offer"]["kind"])

    def test_expired_offer_does_not_erase_independent_current_free_terms(self) -> None:
        rows = sources.parse_cmd(fixture("cmd"))
        offer = {
            "id": "cat-jam:free",
            "name": "Cat Jam",
            "availability": {},
            "tiers": [],
            "deal": {"id": "old", "free": True, "expires": "2020-01-01"},
        }
        sources.annotate_cmd_offers(rows, offer_html([offer]), NOW)
        self.assertIn("free", rows[0].badges)

    def test_zen_discount_never_becomes_a_go_discount_and_expiry_is_enforced(
        self,
    ) -> None:
        for now, qualifies in ((NOW, True), (NOW + 100 * 86400, False)):
            rows = sources.parse_oc(fixture("oc"), "/fixture-project")
            sources.annotate_oc_offers(
                rows, (FIXTURES / "oc-pricing.html").read_text(), now
            )
            by_id = {m.native_id: m for m in rows}
            self.assertEqual(
                qualifies, "deal" in by_id["opencode/gemini-4-argon"].badges
            )
            self.assertNotIn("deal", by_id["opencode-go/gemini-4-argon"].badges)
        html = (FIXTURES / "oc-pricing.html").read_text()
        rows = sources.parse_oc(fixture("oc"), "/fixture-project")
        sources.annotate_oc_offers(
            rows, html.replace("November 30, 2026", "someday"), NOW
        )
        target = next(m for m in rows if m.native_id == "opencode/gemini-4-argon")
        self.assertNotIn("deal", target.badges)
        self.assertEqual("unknown expiry", target.details["offer"]["status"])
        duplicate = "<tr><td>Gemini 4 Argon</td><td>different-route</td><td>https://opencode.ai/inference/google/v1</td><td>sdk</td></tr>"
        with self.assertRaises(sources.SourceError):
            sources.annotate_oc_offers(
                rows, html.replace("</table>", duplicate + "</table>", 1), NOW
            )

    def test_release_dates_native_flags_and_local_observations_are_distinct(
        self,
    ) -> None:
        recent = sources.Model("oc", "opencode/recent", "Recent", released_at=NOW - 60)
        future = sources.Model(
            "oc", "opencode/future", "Future", released_at=NOW + 86400
        )
        old = sources.Model("oc", "opencode/old", "Old", released_at=NOW - 8 * 86400)
        models.add_release_evidence([recent, future, old], NOW)
        self.assertIn("new", recent.badges)
        self.assertNotIn("new", future.badges)
        self.assertNotIn("new", old.badges)

    def test_concurrent_first_seen_merges_and_scopes_do_not_lose_identities(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="am-baseline-") as temp,
            patch.dict(os.environ, XDG_STATE_HOME=temp),
        ):
            script = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from agent_model_sources import Catalog, Model
from agent_models import update_first_seen
os.read(int(sys.argv[2]), 1)
error = update_first_seen([Catalog('cmd', [Model('cmd', sys.argv[3], sys.argv[3])])], '/same-project', float(sys.argv[4]))
if error: raise SystemExit(error)
"""
            self.assertIsNone(
                models.update_first_seen(
                    [
                        sources.Catalog(
                            "cmd", [sources.Model("cmd", "baseline", "Baseline")]
                        )
                    ],
                    "/same-project",
                    NOW,
                )
            )
            reader, writer = os.pipe()
            children = []
            try:
                for native in ("arrived-a", "arrived-b"):
                    children.append(
                        subprocess.Popen(
                            [
                                sys.executable,
                                "-c",
                                script,
                                str(SOURCE),
                                str(reader),
                                native,
                                str(NOW + 1),
                            ],
                            pass_fds=(reader,),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                    )
                os.write(writer, b"xx")
                for child in children:
                    stdout, stderr = child.communicate(timeout=10)
                    self.assertEqual(0, child.returncode, stdout + stderr)
            finally:
                os.close(reader)
                os.close(writer)
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.wait()
            state = json.loads(
                (Path(temp) / "agent-models/first-seen.json").read_text()
            )
            self.assertEqual(
                {"cmd:baseline", "cmd:arrived-a", "cmd:arrived-b"},
                next(iter(state["scopes"].values()))["models"].keys(),
            )
            other = sources.Model("cmd", "arrived-a", "Arrived")
            self.assertIsNone(
                models.update_first_seen(
                    [sources.Catalog("cmd", [other])], "/other-project", NOW + 2
                )
            )
            self.assertNotIn("new", other.badges)


class ShellBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="am-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.helper = self.home / "helper"
        self.helper.mkdir()
        for name in (
            "agent_models.py",
            "agent_model_sources.py",
            "agent_model_picker.py",
        ):
            shutil.copyfile(SOURCE / name, self.helper / name)
        self.offers_path = self.helper / "agent_model_offers.json"
        self.offers_path.write_text(json.dumps({"schema_version": 1, "offers": []}))
        self.log = self.home / "calls.jsonl"
        self.config_path = self.home / "test-config.json"
        self.config = {
            "cmd": [fixture("cmd")],
            "oc": [fixture("oc")],
            "devin": [fixture("devin")],
        }
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.home / "state"),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "TEST_CONFIG": str(self.config_path),
            "TEST_LOG": str(self.log),
            "TEST_OFFERS": str(self.offers_path),
            "AGENT_MODELS_HELPER": str(self.bin / "agent-models"),
        }
        (self.bin / "jq").symlink_to(shutil.which("jq"))
        shim = self.bin / "agent-models"
        shim.write_text(
            f"#!{sys.executable}\n"
            + f"""
import io, json, os, runpy, sys, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, {str(self.helper)!r})
config = json.loads(Path(os.environ['TEST_CONFIG']).read_text())
count = 0
def response(request, **kwargs):
    global count
    url = request.full_url
    if 'view=client' in url:
        sequence = config['cmd']
        data = sequence[min(count, len(sequence)-1)]
        count += 1
        if data == 'unavailable': raise urllib.error.URLError('fixture offline')
        return io.BytesIO(json.dumps(data).encode())
    name = 'cmd' if 'commandcode.ai' in url else 'oc'
    if config.get(name + '_offers') == 'unavailable': raise urllib.error.URLError('fixture offer offline')
    return io.BytesIO(Path({str(FIXTURES)!r}, name + '-pricing.html').read_bytes())
with patch('urllib.request.urlopen', response):
    runpy.run_path({str(self.helper / "agent_models.py")!r}, run_name='__main__')
"""
        )
        shim.chmod(0o755)
        fake = self.bin / "fake-cli"
        fake.write_text(
            f"#!{sys.executable}\n"
            + """
import json, os, sys
from pathlib import Path
config = json.loads(Path(os.environ['TEST_CONFIG']).read_text())
name, args = Path(sys.argv[0]).name, sys.argv[1:]
def log(record):
    with Path(os.environ['TEST_LOG']).open('a') as f: f.write(json.dumps(record) + '\\n')
if name == 'opencode' and args[:2] == ['api', 'model.list'] or name == 'devin' and args[:2] == ['models', 'list']:
    cli = 'oc' if name == 'opencode' else 'devin'
    counter = Path(os.environ['TEST_CONFIG'] + '.' + cli)
    index = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(index+1))
    data = config[cli][min(index, len(config[cli])-1)]
    if cli == 'devin' and index and 'offers_on_recheck' in config:
        Path(os.environ['TEST_OFFERS']).write_text(json.dumps(config['offers_on_recheck']))
    log({'metadata': cli, 'argv': args})
    if data == 'unavailable': sys.exit(19)
    if data == 'truncated': print('{"data":['); sys.exit(0)
    if cli == 'oc' and 'wrong_location' not in config: data['location']['directory'] = os.getcwd()
    print(json.dumps(data)); sys.exit(0)
if name == 'opencode' and args[:2] == ['api', 'session.create']:
    body = json.loads(args[args.index('--data')+1])
    log({'create_session': body})
    if config.get('session_mismatch'): body['model']['id'] = 'wrong'
    print(json.dumps({'data': {'id': 'ses_test', **body}})); sys.exit(0)
if '--list-models' in args or name == 'opencode' and args == ['models']:
    if config.get('fallback_fail'): sys.exit(20)
    print('vendor/fallback  Native description' if name == 'cmd' else 'opencode/native-fallback\\nopenrouter/never-allowed')
    sys.exit(0)
log({'launch': name, 'argv': args, 'stdin': sys.stdin.read(), 'cwd': os.getcwd()})
if name == 'opencode' and args and args[0] == 'run':
    for event in [{'type': 'text', 'part': {'messageID': 'm', 'text': 'FINAL'}}, {'type': 'step_finish', 'part': {'messageID': 'm', 'reason': 'stop'}}]: print(json.dumps(event))
else: print('FINAL')
sys.exit(config.get('native_exit', 0))
"""
        )
        fake.chmod(0o755)
        for cli in ("cmd", "devin", "opencode"):
            (self.bin / cli).symlink_to(fake)

    def run_am(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.config_path.write_text(json.dumps(self.config))
        return subprocess.run(
            [
                BASH,
                "--noprofile",
                "--norc",
                "-c",
                'source "$1"; shift; am "$@"',
                "am-test",
                str(SOURCE / ".bash_agents"),
                *args,
            ],
            cwd=self.home,
            env=self.environment,
            input="literal stdin\n",
            text=True,
            capture_output=True,
            start_new_session=True,
            timeout=20,
            check=False,
        )

    def calls(self) -> list[dict]:
        return (
            [json.loads(line) for line in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )

    def launches(self) -> list[dict]:
        return [call for call in self.calls() if "launch" in call]

    def run_picker(
        self, *, use_fzf: bool, cancel: bool = False, scope: str = "cmd"
    ) -> int:
        self.config_path.write_text(json.dumps(self.config))
        if use_fzf:
            fzf = self.bin / "fzf"
            fzf.write_text(
                f"#!{sys.executable}\n"
                + """
import json, os, shlex, sys
from pathlib import Path
rows = sys.stdin.read().splitlines()
command = sys.argv[sys.argv.index('--preview') + 1]
preview = Path(shlex.split(command)[1].replace('{1}', rows[0].split('\\t')[0]))
with Path(os.environ['TEST_LOG']).open('a') as output:
    output.write(json.dumps({'picker_rows': rows, 'preview': preview.read_text()}) + '\\n')
"""
                + ("sys.exit(130)\n" if cancel else "print(rows[0])\n")
            )
            fzf.chmod(0o755)
        pid, descriptor = pty.fork()
        if pid == 0:
            os.chdir(self.home)
            os.execve(
                BASH,
                [
                    BASH,
                    "--noprofile",
                    "--norc",
                    "-c",
                    'source "$1"; printf "picker stdin\\n" | am "$2" -- -p task',
                    "am-picker-test",
                    str(SOURCE / ".bash_agents"),
                    scope,
                ],
                self.environment,
            )
        deadline = time.monotonic() + 10
        transcript = b""
        answered = False
        try:
            while time.monotonic() < deadline:
                if select.select([descriptor], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(descriptor, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    transcript += chunk
                    if not use_fzf and not answered and b"Model number" in transcript:
                        os.write(descriptor, b"\n" if cancel else b"1\n")
                        answered = True
            else:
                self.fail("picker did not finish")
            _, status = os.waitpid(pid, 0)
            code = os.waitstatus_to_exitcode(status)
            self.assertEqual(0, code, transcript.decode(errors="replace"))
            return code
        finally:
            os.close(descriptor)
            try:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
            except ProcessLookupError:
                pass

    def test_both_pickers_preserve_piped_stdin_and_cancellation_launches_nothing(
        self,
    ) -> None:
        self.environment["NO_COLOR"] = "1"
        for use_fzf in (False, True):
            with self.subTest(use_fzf=use_fzf):
                self.assertEqual(0, self.run_picker(use_fzf=use_fzf))
                self.assertEqual("picker stdin\n", self.launches()[-1]["stdin"])
                before = len(self.launches())
                self.assertEqual(0, self.run_picker(use_fzf=use_fzf, cancel=True))
                self.assertEqual(before, len(self.launches()))
                if use_fzf:
                    screen = next(c for c in self.calls() if "picker_rows" in c)
                    row = screen["picker_rows"][0]
                    self.assertTrue(row.split("\t")[1].startswith("CMD    Cat Jam"))
                    self.assertIn("FREE STEALTH", row)
                    self.assertIn("cmd:stealth/cat-jam:free", row)
                    self.assertIn("stealth reasoning model", row)
                    self.assertNotIn("\033[", row + screen["preview"])
                    self.assertNotIn('{"', screen["preview"])

    def test_rich_list_and_json_are_discovery_only(self) -> None:
        result = self.run_am("cmd", "--list")
        self.assertEqual(0, result.returncode, result.stderr)
        for text in (
            "stealth reasoning model for coding and agentic work",
            "Shared capacity; 100 requests/day",
            "1,048,576 tokens",
            "individual-go",
            "high",
            "while capacity lasts",
            sources.CMD_CATALOG,
            "redacted-client-snapshot",
        ):
            self.assertIn(text, result.stdout)
        self.assertNotIn('{"', result.stdout)
        self.assertNotIn('["', result.stdout)
        self.assertNotIn("\033[", result.stdout)
        self.assertIn("Reference: in $5", result.stdout)
        self.assertIn("Reference: not published", result.stdout)
        result = self.run_am("--all", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual({"cmd", "oc", "devin"}, {s["cli"] for s in data["sources"]})
        mimo = next(
            m for m in data["models"] if m["native_id"] == "xiaomi/mimo-v2.5-pro"
        )
        self.assertIsNone(mimo["details"]["published_tiers"][1]["listRates"])
        self.assertEqual([], self.launches())
        self.assertFalse(any("create_session" in c for c in self.calls()))
        self.assertNotIn("DO_NOT_LEAK", result.stdout)

    def test_native_price_summary_is_not_reported_unpublished(self) -> None:
        result = self.run_am("devin:future-family-high", "--list")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("$1 / 1M Input", result.stdout)
        self.assertNotIn("Token prices: not published", result.stdout)
        result = self.run_am("devin:future-family-beta", "--list")
        self.assertIn("Token prices: not published", result.stdout)
        self.assertEqual([], self.launches())

    def test_picker_prioritizes_current_native_price_over_cost_tier(self) -> None:
        self.environment["NO_COLOR"] = "1"
        self.offers_path.write_text(json.dumps(curated_offers()))
        self.assertEqual(0, self.run_picker(use_fzf=True, scope="devin"))
        screen = next(c for c in self.calls() if "picker_rows" in c)
        row = next(row for row in screen["picker_rows"] if "future-family-high" in row)
        self.assertIn("$1 in", row)
        self.assertIn("$5 out", row)
        self.assertIn("50–75% off (plan)", row)
        self.assertLess(row.index("$1 in"), row.index("50–75%"))
        self.assertNotIn("Low", row)

    def test_changed_curated_terms_stop_deal_launch_at_revalidation(self) -> None:
        expired = curated_offers()
        expired["offers"][0]["through"] = "2020-01-02"
        self.offers_path.write_text(json.dumps(curated_offers()))
        self.config["offers_on_recheck"] = expired
        result = self.run_am(
            "devin:future-family-high", "--kind", "deal", "--", "-p", "task"
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("no longer satisfies --kind deal", result.stderr)
        self.assertEqual([], self.launches())

    def test_curated_offers_reach_lists_json_and_exact_native_launch(self) -> None:
        self.offers_path.write_text(json.dumps(curated_offers()))
        result = self.run_am("devin", "--kind", "deal", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual("curated", data["sources"][0]["offers"])
        self.assertEqual(
            ["devin:future-family-high"], [m["key"] for m in data["models"]]
        )
        self.assertIn("manual", data["models"][0]["details"]["offer_coverage"])
        result = self.run_am("devin:future-family-high", "--kind", "deal", "--list")
        for text in (
            "DEAL",
            "75% off",
            "50% off",
            "2099-12-31",
            "https://example.com/official-pricing",
            "$1 / 1M Input",
        ):
            self.assertIn(text, result.stdout)
        self.assertLess(
            result.stdout.index("$1 / 1M Input"), result.stdout.index("OFFER")
        )
        self.assertEqual([], self.launches())
        result = self.run_am(
            "devin:future-family-high", "--kind", "deal", "--", "-p", "task"
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("future-family-high", self.launches()[0]["argv"][1])

    def test_broken_curated_file_preserves_catalog_and_native_free_evidence(
        self,
    ) -> None:
        for content in ("not JSON", None):
            with self.subTest(content=content):
                if content is None:
                    self.offers_path.unlink()
                else:
                    self.offers_path.write_text(content)
                result = self.run_am("devin", "--all", "--json")
                self.assertEqual(1, result.returncode)
                data = json.loads(result.stdout)
                self.assertEqual("ok", data["sources"][0]["status"])
                self.assertEqual("unavailable", data["sources"][0]["offers"])
                self.assertEqual(4, len(data["models"]))
                self.assertIn("free", data["models"][0]["badges"])
                result = self.run_am(
                    "devin:future-family-high", "--kind", "deal", "--", "-p", "task"
                )
                self.assertNotEqual(0, result.returncode)
                self.assertEqual([], self.launches())

    def test_exact_cmd_alias_colons_literal_arguments_stdin_and_native_status(
        self,
    ) -> None:
        self.config["native_exit"] = 23
        result = self.run_am(
            "cmd:CAT-JAM:FREE",
            "--effort",
            "high",
            "--",
            "--print=--model",
            "literal space # $()",
        )
        self.assertEqual(23, result.returncode, result.stderr)
        call = self.launches()[0]
        self.assertEqual("cmd", call["launch"])
        self.assertEqual(
            [
                "--model",
                "stealth/cat-jam:free",
                "--max-turns",
                "9999",
                "--effort",
                "high",
                "--yolo",
                "--print=--model",
                "literal space # $()",
            ],
            call["argv"],
        )
        self.assertEqual("literal stdin\n", call["stdin"])
        self.assertEqual(str(self.home), call["cwd"])

    def test_opencode_only_zen_go_for_all_query_exact_and_fallback(self) -> None:
        result = self.run_am("oc", "--all", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {"opencode", "opencode-go"},
            {m["native_id"].split("/")[0] for m in json.loads(result.stdout)["models"]},
        )
        result = self.run_am("oc:openrouter/future-coding-free", "--", "-p", "test")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.launches())
        self.config["oc"] = ["unavailable"]
        result = self.run_am("oc", "--all", "--json")
        self.assertEqual(1, result.returncode)
        self.assertEqual(
            ["opencode/native-fallback"],
            [m["native_id"] for m in json.loads(result.stdout)["models"]],
        )

    def test_oc_headless_final_output_variant_and_no_global_pin(self) -> None:
        result = self.run_am(
            "oc:opencode/future-coding-free",
            "--effort",
            "xhigh",
            "--",
            "-p",
            "--format=json",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("FINAL\n", result.stdout)
        call = self.launches()[0]
        self.assertIn("opencode/future-coding-free#xhigh", call["argv"])
        self.assertEqual("--format=json", call["argv"][-1])
        self.assertEqual("literal stdin\n", call["stdin"])
        self.assertFalse((self.home / ".local/state/opencode/model.json").exists())
        self.assertFalse(any("create_session" in c for c in self.calls()))

    def test_oc_tui_uses_verified_session_not_model_state(self) -> None:
        result = self.run_am("oc:opencode/future-coding-free", "--effort", "high")
        self.assertEqual(0, result.returncode, result.stderr)
        body = next(c["create_session"] for c in self.calls() if "create_session" in c)
        self.assertEqual(
            {"id": "future-coding-free", "providerID": "opencode", "variant": "high"},
            body["model"],
        )
        self.assertEqual({"directory": str(self.home)}, body["location"])
        self.assertEqual(
            ["--auto", "--session", "ses_test"], self.launches()[0]["argv"]
        )
        self.assertFalse((self.home / ".local/state/opencode/model.json").exists())

    def test_oc_session_mismatch_stops_launch(self) -> None:
        self.config["session_mismatch"] = True
        result = self.run_am("oc:opencode/future-coding-free")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.launches())

    def test_query_never_autolaunches_and_searches_beyond_shortlist(self) -> None:
        result = self.run_am("cmd", "--list", "Unknown Price")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("vendor/unknown", result.stdout)
        result = self.run_am("cmd", "Unknown Price", "--", "-p", "task")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.launches())

    def test_exact_bypasses_default_shortlist_but_honors_explicit_kind(self) -> None:
        result = self.run_am("cmd:vendor/paid", "--kind", "free", "--", "-p", "task")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual([], self.launches())
        result = self.run_am("cmd:vendor/paid", "--", "-p", "task")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_new_unknown_model_is_launchable_without_registry_edits(self) -> None:
        self.config["cmd"][0]["data"].append(
            {
                "id": "brand/new-never-seen-before",
                "name": "Brand New",
                "display": {"description": "Current native description"},
            }
        )
        result = self.run_am("cmd:brand/new-never-seen-before", "--", "-p", "task")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("brand/new-never-seen-before", self.launches()[0]["argv"])

    def test_revalidation_stops_disappeared_effort_or_changed_free_terms(self) -> None:
        original = fixture("cmd")
        for mutation in ("disappear", "effort", "price"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(original)
                if mutation == "disappear":
                    changed["data"] = changed["data"][1:]
                elif mutation == "effort":
                    changed["data"][0]["reasoningEfforts"] = ["low"]
                else:
                    changed["data"][0]["pricing"] = {"inputCost": 1, "outputCost": 2}
                self.config["cmd"] = [original, changed]
                result = self.run_am(
                    "cmd:stealth/cat-jam:free",
                    "--kind",
                    "free",
                    "--effort",
                    "high",
                    "--",
                    "-p",
                    "task",
                )
                self.assertNotEqual(0, result.returncode)
                self.assertEqual([], self.launches())
                if mutation == "price":
                    result = self.run_am("cmd:stealth/cat-jam:free", "--", "-p", "task")
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual([], self.launches())

    def test_partial_failure_and_offer_failure_are_explicit_json(self) -> None:
        self.config["devin"] = ["unavailable"]
        self.config["cmd_offers"] = "unavailable"
        result = self.run_am("--all", "--json")
        self.assertEqual(1, result.returncode)
        data = json.loads(result.stdout)
        self.assertEqual({"cmd", "oc"}, {m["cli"] for m in data["models"]})
        status = {s["cli"]: s for s in data["sources"]}
        self.assertEqual("unavailable", status["devin"]["status"])
        self.assertEqual("unavailable", status["cmd"]["offers"])
        self.assertEqual("", result.stderr)

    def test_truncated_zero_exit_and_wrong_location_are_not_trusted(self) -> None:
        for config in ({"oc": ["truncated"]}, {"wrong_location": True}):
            self.config["oc"] = [fixture("oc")]
            self.config.update(config)
            self.config["fallback_fail"] = True
            result = self.run_am("oc", "--all", "--json")
            self.assertEqual(1, result.returncode)
            self.assertEqual([], json.loads(result.stdout)["models"])

    def test_effort_identity_and_transport_overrides_fail_without_launch(self) -> None:
        cases = [
            ("cmd:stealth/cat-jam:free", ["--effort", "ultra"]),
            ("devin:swe-2-max", ["--effort", "max"]),
            ("cmd:stealth/cat-jam:free", ["--", "--model=other"]),
            ("oc:opencode/future-coding-free", ["--", "-mother"]),
            ("oc:opencode/future-coding-free", ["--", "--server", "https://other"]),
            ("devin:swe-2-max", ["--", "--resume", "session"]),
            ("cmd:stealth/cat-jam:free", ["--", "-p", "--model", "other"]),
            ("devin:swe-2-max", ["--", "--print", "--model", "other"]),
        ]
        for key, args in cases:
            with self.subTest(key=key, args=args):
                self.assertNotEqual(0, self.run_am(key, *args).returncode)
                self.assertEqual([], self.launches())

    def test_native_devin_variant_and_permission_contract(self) -> None:
        key = "devin:fusion-future-high-sidekick-swe-2-high"
        result = self.run_am(key, "--", "-p", "task")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "--model",
                key.split(":", 1)[1],
                "--permission-mode",
                "dangerous",
                "-p",
                "task",
            ],
            self.launches()[0]["argv"],
        )

    def test_first_baseline_is_not_all_new_and_later_identity_is_locally_new(
        self,
    ) -> None:
        result = self.run_am("cmd", "--kind", "new", "--json")
        self.assertEqual([], json.loads(result.stdout)["models"])
        self.config["cmd"][0]["data"].append(
            {"id": "vendor/arrived", "name": "Arrived"}
        )
        result = self.run_am("cmd", "--kind", "new", "--json")
        self.assertEqual(
            ["vendor/arrived"],
            [m["native_id"] for m in json.loads(result.stdout)["models"]],
        )
        baseline = json.loads(
            (self.home / "state/agent-models/first-seen.json").read_text()
        )
        self.assertEqual({"version", "scopes"}, baseline.keys())
        for scope in baseline["scopes"].values():
            self.assertEqual({"initialized_at", "models"}, scope.keys())
            self.assertTrue(
                all(isinstance(stamp, float) for stamp in scope["models"].values())
            )

    def test_corrupt_baseline_disables_only_local_newness(self) -> None:
        root = self.home / "state/agent-models"
        root.mkdir(parents=True)
        (root / "first-seen.json").write_text("corrupt")
        result = self.run_am("cmd:stealth/cat-jam:free", "--", "-p", "task")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("local-new signal unavailable", result.stderr)

    def test_invalid_baseline_timestamp_never_manufactures_new_models(self) -> None:
        self.assertEqual(0, self.run_am("cmd", "--all", "--json").returncode)
        path = self.home / "state/agent-models/first-seen.json"
        original = json.loads(path.read_text())
        for stamp in (-1, True, 1e30, "yesterday"):
            with self.subTest(stamp=stamp):
                state = copy.deepcopy(original)
                next(iter(state["scopes"].values()))["initialized_at"] = stamp
                path.write_text(json.dumps(state))
                result = self.run_am("cmd", "--kind", "new", "--json")
                self.assertEqual(0, result.returncode, result.stderr)
                data = json.loads(result.stdout)
                self.assertIn("unavailable", data["local_new_status"])
                self.assertEqual([], data["models"])


if __name__ == "__main__":
    unittest.main()
