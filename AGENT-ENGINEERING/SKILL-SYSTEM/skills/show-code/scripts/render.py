#!/usr/bin/env python3
"""Render an authored show-code Markdown file beside its HTML companion."""

from __future__ import annotations

import argparse
import html
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote


ASSETS = Path(__file__).resolve().parents[1] / "assets"


def render(artifact: Path, *, replace: bool = False) -> Path:
    artifact = artifact.resolve(strict=True)
    if artifact.suffix.lower() != ".md":
        raise ValueError("input must be a Markdown .md file")
    output = artifact.with_suffix(".html")
    if output.is_symlink():
        raise FileExistsError(f"refusing to replace symlink {output}")
    if output.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite {output}; use --replace for your own HTML")
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise FileNotFoundError("Pandoc is unavailable; the Markdown artifact remains usable")
    result = subprocess.run(
        [
            pandoc,
            artifact.name,
            "--from=gfm",
            "--to=html5",
            "--standalone",
            "--section-divs",
            "--toc",
            "--toc-depth=2",
            "--highlight-style=pygments",
            f"--template={ASSETS / 'page.html'}",
            f"--variable=page-title:{html.escape(artifact.stem)}",
            f"--variable=source-file:{quote(artifact.name)}",
            f"--variable=styles:{(ASSETS / 'show-code.css').read_text(encoding='utf-8')}",
        ],
        cwd=artifact.parent,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    with output.open("w" if replace else "x", encoding="utf-8") as handle:
        handle.write(result.stdout)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="authored Markdown; HTML stays in the same directory")
    parser.add_argument("--replace", action="store_true", help="regenerate an existing owned HTML file")
    options = parser.parse_args()
    try:
        output = render(options.artifact, replace=options.replace)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"show-code: {exc}\n")
    except subprocess.CalledProcessError as exc:
        parser.exit(1, f"show-code: Pandoc failed: {exc.stderr.strip()}\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
