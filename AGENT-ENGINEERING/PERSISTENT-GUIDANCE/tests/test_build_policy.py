import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "policy" / "scripts"))

from build_policy import EMBEDDED_BLOCKS, embed_block, markers  # noqa: E402
from policylib import PolicyError  # noqa: E402


class EmbedBlockTest(unittest.TestCase):
    def test_packs_without_markers_pass_through_unchanged(self) -> None:
        text = "# Pack\n\n## Applies when\n\nAlways.\n"
        for name in EMBEDDED_BLOCKS:
            with self.subTest(name=name):
                self.assertEqual(embed_block(text, name, "IGNORED"), text)

    def test_marked_region_is_replaced_with_the_cli_block(self) -> None:
        for name in EMBEDDED_BLOCKS:
            begin, end = markers(name)
            with self.subTest(name=name):
                self.assertEqual(
                    embed_block(f"# Pack\n\n{begin}\nstale\n{end}\n", name, "## Block\n- fresh"),
                    f"# Pack\n\n{begin}\n## Block\n- fresh\n{end}\n",
                )

    def test_one_block_leaves_another_blocks_region_alone(self) -> None:
        omem_begin, omem_end = markers("OMEM INSTRUCTIONS")
        hist_begin, hist_end = markers("HIST INSTRUCTIONS")
        text = f"{hist_begin}\nold hist\n{hist_end}\n\n{omem_begin}\nold memory\n{omem_end}\n"
        self.assertEqual(
            embed_block(text, "OMEM INSTRUCTIONS", "new memory"),
            f"{hist_begin}\nold hist\n{hist_end}\n\n{omem_begin}\nnew memory\n{omem_end}\n",
        )

    def test_malformed_markers_fail_the_build(self) -> None:
        for name in EMBEDDED_BLOCKS:
            begin, end = markers(name)
            for text in (f"{begin}\n", f"{end}\n", f"{begin}\n{end}\n{begin}\n{end}\n"):
                with self.subTest(name=name, text=text):
                    with self.assertRaises(PolicyError):
                        embed_block(text, name, "block")


if __name__ == "__main__":
    unittest.main()
