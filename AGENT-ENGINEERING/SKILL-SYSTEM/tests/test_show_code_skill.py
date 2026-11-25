from __future__ import annotations

from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skill_system import SkillSystem, content_hash
from skill_system.model import validate_skill_tree


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "show-code"
SPEC = importlib.util.spec_from_file_location("show_code_render", SKILL / "scripts" / "render.py")
assert SPEC is not None and SPEC.loader is not None
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


class RenderedPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


class ShowCodePackageTests(unittest.TestCase):
    def test_package_is_self_contained_and_registers_its_own_identity(self) -> None:
        validate_skill_tree(SKILL, "show-code")
        registry = json.loads((ROOT / "registry.json").read_text())["skills"]
        self.assertEqual("skills/show-code", registry["show-code"]["source"])
        self.assertEqual(["~/.agents/skills/show-code"], registry["show-code"]["install_targets"])
        self.assertEqual("local-write", registry["show-code"]["effect_ceiling"])
        self.assertEqual([], registry["show-code"]["dependencies"])
        for name in ("show-me-clearly", "explain-code"):
            self.assertNotEqual(registry[name]["source"], registry["show-code"]["source"])
        for asset in ("walkthrough.md", "page.html", "show-code.css"):
            self.assertTrue((SKILL / "assets" / asset).is_file())

    def test_managed_install_dry_run_idempotence_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            system = SkillSystem(ROOT, home)
            target = home / ".agents" / "skills" / "show-code"
            self.assertEqual("dry-run", system.install("show-code", apply=False).reason)
            self.assertFalse(target.exists())
            result = system.install("show-code", apply=True)
            self.assertTrue(result.applied)
            self.assertEqual(content_hash(SKILL), content_hash(target))
            self.assertEqual("already-current", system.install("show-code", apply=True).reason)
            self.assertIsNotNone(result.operation_id)
            system.rollback(result.operation_id, apply=True)
            self.assertFalse(target.exists())
            self.assertEqual((), system.status().incomplete_operations)


class ShowCodeRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve() / "code explanation with spaces"
        self.directory.mkdir()
        self.artifact = self.directory / "selection & return-20260907.md"
        self.markdown = """# Exact selection

## Scope

The input comes from the reducer.

<div class="code-pair">

```typescript
const selected = priceAt(input.price);
```

<div class="explanation">

The chart and readout consume the same value.

</div>

</div>

[Source](example.ts#L1)

## Keep this line

An exact point reaches both consumers.
"""
        self.artifact.write_text(self.markdown)
        (self.directory / "example.ts").write_text("const selected = priceAt(input.price);\n")

    @unittest.skipUnless(shutil.which("pandoc"), "Pandoc is required for the real rendering test")
    def test_cli_renders_sibling_html_with_semantic_pairs_and_unchanged_links(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SKILL / "scripts" / "render.py"), str(self.artifact)],
            cwd=self.directory.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        output = self.artifact.with_suffix(".html")
        self.assertEqual(str(output), completed.stdout.strip())
        self.assertEqual(self.markdown, self.artifact.read_text())
        parsed = RenderedPage()
        parsed.feed(output.read_text())
        self.assertTrue(any(tag == "style" for tag, _ in parsed.tags))
        self.assertFalse(any(tag in {"script", "link"} for tag, _ in parsed.tags))
        self.assertTrue(any(attrs.get("class") == "code-pair" for _, attrs in parsed.tags))
        self.assertTrue(any(attrs.get("class") == "explanation" for _, attrs in parsed.tags))
        self.assertTrue(any(tag == "h1" for tag, _ in parsed.tags))
        self.assertTrue(any(tag == "nav" for tag, _ in parsed.tags))
        hrefs = [attrs["href"] for tag, attrs in parsed.tags if tag == "a"]
        self.assertIn("example.ts#L1", hrefs)
        self.assertIn("selection%20%26%20return-20260907.md", hrefs)
        self.assertIn("const selected = priceAt(input.price);", "".join(parsed.text))
        self.assertIn("The chart and readout consume the same value.", "".join(parsed.text))

    def test_existing_output_is_preserved_without_replace(self) -> None:
        output = self.artifact.with_suffix(".html")
        output.write_text("existing result")
        with self.assertRaises(FileExistsError):
            RENDERER.render(self.artifact)
        self.assertEqual("existing result", output.read_text())

    @unittest.skipUnless(shutil.which("pandoc"), "Pandoc is required for replacement rendering")
    def test_explicit_replace_regenerates_owned_html(self) -> None:
        output = self.artifact.with_suffix(".html")
        output.write_text("old result")
        self.assertEqual(output, RENDERER.render(self.artifact, replace=True))
        self.assertTrue(output.read_text().startswith("<!doctype html>"))

    def test_symlink_output_is_not_followed_even_with_replace(self) -> None:
        other = self.directory / "unrelated.html"
        other.write_text("keep me")
        self.artifact.with_suffix(".html").symlink_to(other)
        with self.assertRaises(FileExistsError):
            RENDERER.render(self.artifact, replace=True)
        self.assertEqual("keep me", other.read_text())

    def test_missing_pandoc_does_not_create_output_or_modify_markdown(self) -> None:
        with patch.object(RENDERER.shutil, "which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                RENDERER.render(self.artifact)
        self.assertFalse(self.artifact.with_suffix(".html").exists())
        self.assertEqual(self.markdown, self.artifact.read_text())

    def test_failed_pandoc_preserves_existing_output(self) -> None:
        output = self.artifact.with_suffix(".html")
        output.write_text("previous result")
        error = subprocess.CalledProcessError(7, ["pandoc"], stderr="render failed")
        with patch.object(RENDERER.shutil, "which", return_value="pandoc"):
            with patch.object(RENDERER.subprocess, "run", side_effect=error):
                with self.assertRaises(subprocess.CalledProcessError):
                    RENDERER.render(self.artifact, replace=True)
        self.assertEqual("previous result", output.read_text())


if __name__ == "__main__":
    unittest.main()
