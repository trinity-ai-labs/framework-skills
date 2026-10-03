import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from support import FIXTURES, snapshot, tool


class CheckCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.api = self.tmp / "api"
        self.api.mkdir()
        (self.api / "9.9.9.json").write_text(tool.dump_snapshot(snapshot("v1", "9.9.9")))
        self.chapters = self.tmp / "chapters"
        self.chapters.mkdir()

    def run_check(self, *fixture_names):
        for n in fixture_names:
            shutil.copy(FIXTURES / "chapters" / n, self.chapters / n)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tool.main(["check", "--chapters-dir", str(self.chapters), "--api-dir", str(self.api)])
        return code, out.getvalue(), err.getvalue()

    def test_good_chapter_passes_and_ignores_non_module_dotted_names(self):
        code, out, err = self.run_check("good.md")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("checked 1 chapter", out)

    def test_nonexistent_export_fails_naming_file_and_symbol(self):
        code, _, err = self.run_check("badsymbol.md")
        self.assertNotEqual(code, 0)
        self.assertIn("badsymbol.md", err)
        self.assertIn("Effect.doesNotExist", err)
        self.assertIn("Array.nope", err)  # a JS global name does not excuse a symbol neither side has
        self.assertNotIn("Effect.succeed", err)

    def test_chapter_without_stamp_fails_naming_the_file(self):
        code, _, err = self.run_check("nostamp.md")
        self.assertNotEqual(code, 0)
        self.assertIn("nostamp.md", err)

    def test_malformed_stamp_fails(self):
        code, _, err = self.run_check("malformed.md")
        self.assertNotEqual(code, 0)
        self.assertIn("malformed.md", err)

    def test_stamped_version_without_snapshot_fails_saying_so(self):
        code, _, err = self.run_check("unknownversion.md")
        self.assertNotEqual(code, 0)
        self.assertIn("unknownversion.md", err)
        self.assertIn("no committed snapshot", err)

    def test_missing_directory_exits_zero_and_says_zero_checked(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tool.main(["check", "--chapters-dir", str(self.tmp / "absent"), "--api-dir", str(self.api)])
        self.assertEqual(code, 0)
        self.assertIn("checked 0 chapters", out.getvalue())

    def test_empty_directory_exits_zero_and_says_zero_checked(self):
        code, out, _ = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("checked 0 chapters", out)

    def test_generated_files_in_subdirectories_are_not_chapters(self):
        (self.chapters / "changes").mkdir()
        shutil.copy(FIXTURES / "chapters" / "nostamp.md", self.chapters / "changes" / "4.1.0.md")
        code, out, _ = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("checked 0 chapters", out)

    def test_ambiguous_basename_fails_only_when_no_module_has_the_export(self):
        (self.chapters / "r.md").write_text(
            "<!-- verified: effect@9.9.9 -->\n`Router.add` `Router.onlyInRpc` `Router.missing`\n")
        code, _, err = self.run_check()
        self.assertNotEqual(code, 0)
        self.assertIn("Router.missing", err)
        self.assertNotIn("Router.add", err)
        self.assertNotIn("Router.onlyInRpc", err)


if __name__ == "__main__":
    unittest.main()
