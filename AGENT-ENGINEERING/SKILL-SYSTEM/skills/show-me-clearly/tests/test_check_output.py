from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_output.py"
SPEC = importlib.util.spec_from_file_location("check_output", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
check_output = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_output
SPEC.loader.exec_module(check_output)


class OutputCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "worker.py"
        self.source.write_text("first\nsecond\nthird\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_artifact(self, name: str, body: str) -> Path:
        artifact = self.root / name
        artifact.write_text(body)
        return artifact

    def valid_body(self) -> str:
        return """# Explanation

## Map

<pre>
<span style="color:#0969da"><strong>■ ENTER</strong></span> request
   |
   `--&gt; <span style="color:#1a7f37"><strong>■ RETURN</strong></span> result
</pre>

[worker.py:1-2](worker.py#L1)
"""

    def test_accepts_color_assisted_visual_and_resolved_source_link(self) -> None:
        artifact = self.write_artifact(
            "worker-explanation-20260823.md", self.valid_body()
        )

        errors, visuals, links = check_output.check_artifact(artifact)

        self.assertEqual([], errors)
        self.assertEqual(1, visuals)
        self.assertEqual(1, links)

    def test_rejects_wrong_filename_and_missing_source_link(self) -> None:
        artifact = self.write_artifact(
            "worker.md",
            """# Explanation

```text
request --> result
```
""",
        )

        errors, _, _ = check_output.check_artifact(artifact)

        self.assertIn("artifact name must end with -YYYYMMDD.md", errors)
        self.assertIn(
            "no repository-relative source link with a #L line anchor found",
            errors,
        )

    def test_rejects_visual_over_line_and_width_limits(self) -> None:
        lines = "\n".join(f"step {number}" for number in range(17))
        artifact = self.write_artifact(
            "worker-explanation-20260823.md",
            f"""# Explanation

## Map

```text
{lines}
{'x' * 89}
```

[worker.py:1-2](worker.py#L1)
""",
        )

        errors, _, _ = check_output.check_artifact(artifact)

        self.assertTrue(any("18 nonblank lines" in error for error in errors))
        self.assertTrue(any("89 columns wide" in error for error in errors))

    def test_zoom_uses_twelve_line_limit(self) -> None:
        lines = "\n".join(f"state {number}" for number in range(13))
        artifact = self.write_artifact(
            "worker-explanation-20260823.md",
            f"""# Explanation

## Zoom — retry state

```text
{lines}
```

[worker.py:1-2](worker.py#L1)
""",
        )

        errors, _, _ = check_output.check_artifact(artifact)

        self.assertTrue(any("limit is 12" in error for error in errors))

    def test_rejects_broken_or_out_of_range_links(self) -> None:
        artifact = self.write_artifact(
            "worker-explanation-20260823.md",
            """# Explanation

```text
request --> result
```

[missing.py:1](missing.py#L1)
[worker.py:99](worker.py#L99)
""",
        )

        errors, _, _ = check_output.check_artifact(artifact)

        self.assertTrue(any("broken local link" in error for error in errors))
        self.assertTrue(any("starts at line 99" in error for error in errors))

    def test_line_ranges_must_end_after_they_start_and_inside_the_file(self) -> None:
        self.source.write_text("".join(f"line {number}\n" for number in range(1, 31)))
        cases = (
            ("[worker.py:2-30](worker.py#L2-L30)", None),
            ("[`worker.py:4-6`](worker.py#L4)", None),
            ("[worker.py:5](worker.py#L5-L5)", None),
            ("[worker.py:10-9999](worker.py#L10-L9999)", "ends at line 9999"),
            ("[worker.py:20-10](worker.py#L20-L10)", "ends before it starts"),
            ("[`worker.py:5-31`](worker.py#L5)", "ends at line 31"),
            ("[`worker.py:12-8`](worker.py#L12)", "ends before it starts"),
        )
        for link, expected in cases:
            with self.subTest(link=link):
                artifact = self.write_artifact(
                    "worker-explanation-20260823.md",
                    f"""# Explanation

```text
request --> result
```

{link}
""",
                )

                errors, _, links = check_output.check_artifact(artifact)

                self.assertEqual(1, links)
                if expected is None:
                    self.assertEqual([], errors)
                else:
                    self.assertEqual(1, len(errors), errors)
                    self.assertIn(expected, errors[0])


if __name__ == "__main__":
    unittest.main()
