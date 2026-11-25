from __future__ import annotations

import unittest

from scan_helpers import TemporaryGitRepo

from runtime.analysis.git_snapshot import (
    ChangeKind,
    GitSnapshotError,
    SnapshotConfig,
    SnapshotScopeError,
    capture_snapshot,
)


class GitSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TemporaryGitRepo()

    def tearDown(self) -> None:
        self.repo.close()

    def test_requires_full_frozen_object_ids(self) -> None:
        self.repo.write("module.py", "VALUE = 1\n")
        before = self.repo.commit("base")
        self.repo.write("module.py", "VALUE = 2\n")
        after = self.repo.commit("change")

        with self.assertRaisesRegex(GitSnapshotError, "full lowercase"):
            capture_snapshot(self.repo.path, "HEAD^", after)
        snapshot = capture_snapshot(self.repo.path, before, after)

        self.assertEqual(before, snapshot.commit_range.before)
        self.assertEqual(after, snapshot.commit_range.after)
        self.assertEqual((after,), snapshot.ordered_commits)
        self.assertFalse(snapshot.first_parent_resolution)

    def test_reads_committed_blobs_not_dirty_worktree(self) -> None:
        self.repo.write("module.py", "VALUE = 'before'\n")
        before = self.repo.commit("base")
        self.repo.write("module.py", "VALUE = 'committed'\n")
        after = self.repo.commit("change")
        self.repo.write("module.py", "VALUE = 'dirty'\n")

        snapshot = capture_snapshot(self.repo.path, before, after)

        self.assertEqual(b"VALUE = 'before'\n", snapshot.python_files[0].before_blob)
        self.assertEqual(b"VALUE = 'committed'\n", snapshot.python_files[0].after_blob)
        self.assertNotIn(b"dirty", snapshot.python_files[0].after_blob or b"")

    def test_initial_and_multi_commit_ranges_are_exact(self) -> None:
        self.repo.write("one.py", "ONE = 1\n")
        first = self.repo.commit("first")
        initial = capture_snapshot(self.repo.path, self.repo.empty_tree(), first)
        self.assertEqual(1, initial.commit_range.commits)
        self.assertEqual((first,), initial.ordered_commits)

        self.repo.write("one.py", "ONE = 2\n")
        second = self.repo.commit("second")
        self.repo.write("two.py", "TWO = 2\n")
        third = self.repo.commit("third")
        multi = capture_snapshot(self.repo.path, first, third)

        self.assertEqual(2, multi.commit_range.commits)
        self.assertEqual((second, third), multi.ordered_commits)

    def test_nul_safe_name_status_preserves_newline_path(self) -> None:
        self.repo.write("base.txt", "base\n")
        before = self.repo.commit("base")
        odd_path = "odd\nname.py"
        self.repo.write(odd_path, "VALUE = 1\n")
        after = self.repo.commit("odd path")

        snapshot = capture_snapshot(self.repo.path, before, after)

        self.assertEqual((odd_path,), tuple(item.path for item in snapshot.python_files))

    def test_exact_rename_delete_and_ambiguous_rename_are_typed(self) -> None:
        self.repo.write("old.py", "def stable():\n    return 1\n")
        before = self.repo.commit("base")
        self.repo.git("mv", "old.py", "renamed.py")
        exact = self.repo.commit("exact rename")

        snapshot = capture_snapshot(self.repo.path, before, exact)
        self.assertEqual(ChangeKind.RENAMED_EXACT, snapshot.python_files[0].change)
        self.assertEqual("old.py", snapshot.python_files[0].old_path)

        self.repo.remove("renamed.py")
        deleted = self.repo.commit("delete")
        snapshot = capture_snapshot(self.repo.path, exact, deleted)
        self.assertEqual(ChangeKind.DELETED, snapshot.python_files[0].change)
        self.assertIsNone(snapshot.python_files[0].after_blob)

        self.repo.write(
            "source.py",
            "\n".join("VALUE_{} = {}".format(index, index) for index in range(40))
            + "\n",
        )
        rename_before = self.repo.commit("rename base")
        self.repo.git("mv", "source.py", "destination.py")
        self.repo.write(
            "destination.py",
            "\n".join(
                "VALUE_{} = {!r}".format(index, "changed" if index < 8 else index)
                for index in range(40)
            )
            + "\n",
        )
        rename_after = self.repo.commit("rename and modify")
        snapshot = capture_snapshot(self.repo.path, rename_before, rename_after)
        self.assertEqual(ChangeKind.RENAMED_AMBIGUOUS, snapshot.python_files[0].change)

    def test_scope_overflow_retains_complete_file_manifest(self) -> None:
        self.repo.write("base.txt", "base\n")
        before = self.repo.commit("base")
        self.repo.write("one.py", "ONE = 1\n")
        self.repo.write("two.py", "TWO = 2\n")
        after = self.repo.commit("two files")

        with self.assertRaises(SnapshotScopeError) as captured:
            capture_snapshot(
                self.repo.path,
                before,
                after,
                config=SnapshotConfig(max_python_files=1),
            )

        self.assertEqual(("one.py", "two.py"), captured.exception.paths)

    def test_non_python_range_skips_blob_materialization(self) -> None:
        self.repo.write("notes.txt", "one\n")
        before = self.repo.commit("base")
        self.repo.write("notes.txt", "two\n")
        after = self.repo.commit("change")

        snapshot = capture_snapshot(self.repo.path, before, after)

        self.assertEqual((), snapshot.python_files)
        self.assertEqual(1, snapshot.files_changed)


if __name__ == "__main__":
    unittest.main()
