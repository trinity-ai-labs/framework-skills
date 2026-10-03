import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import tarball, tool


class SnapshotCommand(unittest.TestCase):
    def run_once(self, tmp, name):
        tgz = Path(tmp) / "pkg.tgz"
        tgz.write_bytes(tarball("v1"))
        out = Path(tmp) / name
        with redirect_stdout(io.StringIO()):
            code = tool.main(["snapshot", "9.9.9", "--tarball", str(tgz), "--api-dir", str(out)])
        self.assertEqual(code, 0)
        return (out / "9.9.9.json").read_bytes()

    def test_two_runs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.run_once(tmp, "a"), self.run_once(tmp, "b")
        self.assertEqual(hashlib.sha256(a).digest(), hashlib.sha256(b).digest())

    def test_output_is_sorted_json_without_timestamps(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            raw = self.run_once(tmp, "a").decode()
        snap = json.loads(raw)
        self.assertEqual(list(snap["modules"]), sorted(snap["modules"]))
        names = [e["name"] for e in snap["modules"]["effect/Effect"]["exports"]]
        self.assertEqual(names, sorted(names))
        self.assertTrue(raw.endswith("}\n"))

    def test_bad_version_fails(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(["snapshot", "../x", "--api-dir", tmp]), 1)


if __name__ == "__main__":
    unittest.main()
