"""Shared helpers: load the tool and build snapshots from the fixture trees."""
import io
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import api_snapshot as tool  # noqa: E402

FIXTURES = HERE / "fixtures"


def dts_files(tree):
    root = FIXTURES / tree / "dist"
    return {str(p.relative_to(root)): p.read_text() for p in root.rglob("*.d.ts")}


def snapshot(tree, version):
    return tool.build_snapshot(dts_files(tree), version)


def tarball(tree):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, text in sorted(dts_files(tree).items()):
            data = text.encode()
            info = tarfile.TarInfo("package/dist/" + rel)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def exports(snap, spec):
    return {(e["name"], e["bucket"]): e for e in snap["modules"][spec]["exports"]}
