import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path

from support import snapshot, tarball, tool

CHANGELOG = "# Changelog\n\nPreamble about versions.\n\n## 1.0.1\n\n- older entry\n\n## 1.0.0\n\n- first\n"
MANIFEST = '{\n  "name": "frameworks",\n  "version": "1.0.1",\n  "license": "MIT"\n}\n'


class Repo:
    """A throwaway repository root with one snapshot (9.9.9), a manifest and a changelog."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "api" / "effect").mkdir(parents=True)
        (self.root / "api" / "effect" / "9.9.9.json").write_text(tool.dump_snapshot(snapshot("v1", "9.9.9")))
        (self.root / ".claude-plugin").mkdir()
        (self.root / ".claude-plugin" / "plugin.json").write_text(MANIFEST)
        (self.root / "CHANGELOG.md").write_text(CHANGELOG)
        self.tgz_dir = tempfile.TemporaryDirectory()
        self.tgz = Path(self.tgz_dir.name) / "v2.tgz"
        self.tgz.write_bytes(tarball("v2"))

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*")) if p.is_file()}

    def watch(self, latest, *extra):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = tool.main(["watch", "--repo-root", str(self.root), "--latest", latest,
                            "--tarball", str(self.tgz), *extra])
        return rc, out.getvalue(), err.getvalue()

    def cleanup(self):
        self.tgz_dir.cleanup()
        self.tmp.cleanup()


class Watch(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.cleanup)

    def test_equal_versions_change_nothing(self):
        before = self.repo.files()
        rc, out, _ = self.repo.watch("9.9.9")
        self.assertEqual(rc, 0)
        self.assertIn("nothing changed: effect@9.9.9 is the newest snapshot", out)
        self.assertEqual(before, self.repo.files())

    def test_older_or_prerelease_latest_changes_nothing(self):
        before = self.repo.files()
        for latest in ("9.9.8", "9.10.0-beta.1"):
            rc, out, _ = self.repo.watch(latest)
            self.assertEqual(rc, 0)
            self.assertIn("nothing changed", out)
        self.assertEqual(before, self.repo.files())

    def test_newer_release_is_recorded_end_to_end(self):
        rc, out, err = self.repo.watch("9.9.10")
        self.assertEqual((rc, err), (0, ""))
        self.assertIn("recorded: 9.9.10", out)
        root = self.repo.root
        self.assertTrue((root / "api" / "effect" / "9.9.10.json").is_file())
        changes = (root / "skills/effect-v4/reference/changes/9.9.10.md").read_text()
        self.assertIn("effect@9.9.9", changes)
        self.assertIn("effect@9.9.10", changes)
        self.assertIn("watch", changes.split("\n## ", 1)[0])
        self.assertIn("`map` [stable]: removed", changes)
        self.assertIn('"version": "1.0.2"', (root / ".claude-plugin/plugin.json").read_text())
        log = (root / "CHANGELOG.md").read_text()
        self.assertLess(log.index("Preamble"), log.index("## 1.0.2"))
        self.assertLess(log.index("## 1.0.2"), log.index("## 1.0.1"))
        self.assertIn("Recorded the `effect@9.9.10` release", log)
        self.assertIn("skills/effect-v4/reference/changes/9.9.10.md", log)

    def test_rerun_changes_nothing_more(self):
        self.repo.watch("9.9.10")
        after_first = self.repo.files()
        rc, out, _ = self.repo.watch("9.9.10")
        self.assertEqual(rc, 0)
        self.assertIn("nothing changed", out)
        self.assertEqual(after_first, self.repo.files())

    def test_interrupted_run_is_finished_without_a_second_bump(self):
        self.repo.watch("9.9.10")
        (self.repo.root / "skills/effect-v4/reference/changes/9.9.10.md").unlink()
        rc, _, _ = self.repo.watch("9.9.10")
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo.root / "skills/effect-v4/reference/changes/9.9.10.md").is_file())
        self.assertIn('"version": "1.0.2"', (self.repo.root / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((self.repo.root / "CHANGELOG.md").read_text().count("## 1.0.2"), 1)

    def test_skipped_release_is_visible_in_the_file(self):
        self.repo.watch("9.9.12")
        changes = (self.repo.root / "skills/effect-v4/reference/changes/9.9.12.md").read_text()
        self.assertIn("effect@9.9.9", changes)
        self.assertIn("effect@9.9.12", changes)

    def test_failed_snapshot_leaves_the_version_files_alone(self):
        before = self.repo.files()
        rc, _, err = self.repo.watch("9.9.10", "--tarball", "/no/such.tgz")
        self.assertEqual(rc, 1)
        self.assertIn("snapshot failed", err)
        self.assertEqual(before, self.repo.files())

    def test_no_snapshot_to_compare_with_fails(self):
        (self.repo.root / "api/effect/9.9.9.json").unlink()
        self.assertEqual(self.repo.watch("9.9.10")[0], 1)

    def test_not_a_version_is_refused(self):
        self.assertEqual(self.repo.watch("latest")[0], 1)


class Semver(unittest.TestCase):
    def test_orders_by_number_not_by_string(self):
        vs = ["4.0.10", "4.0.9", "4.10.0", "4.2.0", "10.0.0", "4.0.0"]
        self.assertEqual(sorted(vs, key=tool.semver_key), ["4.0.0", "4.0.9", "4.0.10", "4.2.0", "4.10.0", "10.0.0"])

    def test_release_sorts_after_its_prereleases(self):
        vs = ["4.0.0", "4.0.0-rc.10", "4.0.0-rc.2", "4.0.0-beta"]
        self.assertEqual(sorted(vs, key=tool.semver_key), ["4.0.0-beta", "4.0.0-rc.2", "4.0.0-rc.10", "4.0.0"])

    def test_newest_snapshot_is_chosen_by_semver(self):
        with tempfile.TemporaryDirectory() as d:
            for v in ("4.0.9", "4.0.10", "4.0.2"):
                (Path(d) / (v + ".json")).write_text("{}")
            (Path(d) / "notes.json").write_text("{}")
            self.assertEqual(tool.snapshot_versions(d)[-1], "4.0.10")

    def test_patch_bump_edits_only_the_version(self):
        text, new = tool.bump_plugin_patch(MANIFEST)
        self.assertEqual(new, "1.0.2")
        self.assertEqual(text, MANIFEST.replace("1.0.1", "1.0.2"))


if __name__ == "__main__":
    unittest.main()
