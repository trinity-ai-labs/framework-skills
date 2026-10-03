#!/usr/bin/env python3
"""Snapshot, diff and check the public API of the published `effect` package.

Usage (run `--help` on any command for its options):

  api_snapshot.py snapshot <version>     download effect@<version>, write api/effect/<version>.json
  api_snapshot.py diff <a.json> <b.json> Markdown report of what changed, grouped by stability tier
  api_snapshot.py changes <a.json> <b.json>  render the breaking-changes file for a release
  api_snapshot.py watch                  record a new `effect` release: snapshot, changes file, version bump
  api_snapshot.py check                  fail on a chapter naming an export its stamped version lacks

Exit codes: 0 success; 1 the command ran and found a problem (check failures,
download or parse errors); 2 bad command line.  Python 3.10+, standard library only.
Only `snapshot` and `watch` touch the network.  The JSON layout is private to this tool:
drive it through the command line.
"""
import argparse
import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API_DIR = REPO_ROOT / "api" / "effect"
DEFAULT_CHAPTERS_DIR = REPO_ROOT / "skills" / "effect-v4" / "reference"
REGISTRY = "https://registry.npmjs.org"
SCHEMA = 1
_SEMVER = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?"
STAMP_RE = re.compile(r"^<!-- verified: effect@(%s) -->$" % _SEMVER)
VERSION_RE = re.compile("^%s$" % _SEMVER)

# ---------------------------------------------------------------- parsing .d.ts
#
# The input is tsc's declaration output, so a small scanner is enough: it splits a
# file into top-level statements by bracket depth (ignoring comments and strings),
# then reads the head of each.  Template-literal `${}` nesting is not tracked.

_SIG = re.compile(
    r"""/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`|[(){}\[\];]""",
    re.S,
)
_COMMENT_OR_STRING = re.compile(
    r"""(/\*.*?\*/|//[^\n]*)|("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)""", re.S
)
_BLOCK_HEAD = re.compile(
    r"(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?(?:class|interface|namespace|module|enum|const\s+enum)\b|declare\s+global\b"
)
_DECL = re.compile(
    r"^(?P<export>export\s+)?(?:declare\s+)?(?:abstract\s+)?"
    r"(?P<kind>const\s+enum|enum|class|function|const|let|var|namespace|interface|type)"
    r"\s+(?P<name>[A-Za-z_$][\w$]*)"
)
_EXPORT_LIST = re.compile(r"^export\s+(?P<type>type\s+)?\{", re.S)
_EXPORT_STAR = re.compile(r"""^export\s+\*\s+(?:as\s+(?P<name>[\w$]+)\s+)?from\s+["'](?P<src>[^"']+)["']""")
_FROM = re.compile(r"""\}\s*from\s*["']([^"']+)["']\s*;?\s*$""")
_REST_OF_LINE = re.compile(r"(?P<tail>[^\n]*)")

BUCKET = {
    "const": "value", "let": "value", "var": "value", "function": "value",
    "class": "value", "enum": "value", "const enum": "value",
    "interface": "type", "type": "type", "namespace": "namespace",
}


def scan(src):
    """Split source into (preceding /** doc or None, raw text) top-level statements."""
    out, i, n, doc = [], 0, len(src), None
    ws = re.compile(r"\s+")
    while i < n:
        m = ws.match(src, i)
        if m:
            i = m.end()
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            if src.startswith("/**", i):
                doc = src[i:j]
            i = j
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j + 1
        elif src[i] == ";":
            i += 1
        else:
            end = _statement_end(src, i)
            out.append((doc, src[i:end]))
            doc, i = None, end
    return out


def _statement_end(src, start):
    block = bool(_BLOCK_HEAD.match(src, start))
    depth = 0
    for m in _SIG.finditer(src, start):
        t = m.group()
        if t in "([{":
            depth += 1
        elif t in ")]}":
            depth -= 1
            if depth == 0 and t == "}" and block:
                # A block's closing brace ends its line (`}` or `};`); a brace in the
                # head, as in `extends Foo<{..}[number]> {`, is followed by more code.
                rest = _REST_OF_LINE.match(src, m.end())
                tail = rest["tail"].strip()
                if tail in ("", ";"):
                    return m.end() + (rest["tail"].index(";") + 1 if tail else 0)
        elif t == ";" and depth == 0:
            return m.end()
    return len(src)


def strip(raw):
    """Comments removed, whitespace collapsed: the form that is hashed and parsed."""
    return " ".join(_COMMENT_OR_STRING.sub(lambda m: " " if m.group(1) else m.group(2), raw).split())


def tags(doc):
    """(since, stability) from a doc comment's own tag lines; stability defaults to stable."""
    def find(tag):
        m = re.search(r"(?m)^[ \t]*(?:/\*\*)?[ \t]*\*?[ \t]*@" + tag + r"[ \t]+([^\s*]+)", doc or "")
        return m.group(1) if m else None
    return find("since"), find("stability") or "stable"


def _digest(parts):
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


class ModuleParser:
    """Collects the exports of one .d.ts file, keyed by (name, bucket)."""

    def __init__(self):
        self.entries = {}
        self.locals = {}

    def add(self, name, kind, bucket, doc, text):
        e = self.entries.get((name, bucket))
        if e is None:
            e = self.entries[(name, bucket)] = {"kind": kind, "doc": None, "parts": []}
        e["parts"].append(text)
        if e["doc"] is None and doc is not None:  # overloads share the first signature's doc
            e["doc"] = doc

    def parse(self, src, prefix="", in_namespace=False):
        for doc, raw in scan(src):
            text = strip(raw)
            if not text:
                continue
            m = _DECL.match(text)
            if m and (m["export"] or in_namespace):
                self._declaration(m, doc, raw, text, prefix)
            elif m:
                kind = m["kind"]
                self.locals.setdefault(m["name"], []).append((kind, text))
            elif _EXPORT_LIST.match(text):
                self._export_list(raw, text)
            elif text.startswith("export"):
                s = _EXPORT_STAR.match(text)
                if s:
                    name = s["name"] or "*"
                    self.add(name, "module" if s["name"] else "star", "value", doc, text)
                elif text.rstrip(";").strip() != "export {}" and not in_namespace:
                    raise ValueError("unrecognised export statement: " + text[:100])

    def _declaration(self, m, doc, raw, text, prefix):
        kind = m["kind"]
        name = prefix + m["name"]
        self.add(name, kind, BUCKET[kind], doc, text)
        if kind == "namespace":
            self.parse(raw[raw.index("{") + 1:raw.rindex("}")], name + ".", True)

    def _export_list(self, raw, text):
        body = raw[raw.index("{") + 1:raw.rindex("}")]
        docs = []

        def stash(mm):
            if mm.group().startswith("/**"):
                docs.append(mm.group())
                return "\x00%d\x00" % (len(docs) - 1)
            return " "
        body = re.sub(r"/\*.*?\*/|//[^\n]*", stash, body, flags=re.S)
        source = _FROM.search(raw)
        type_only = bool(_EXPORT_LIST.match(text)["type"])
        for item in body.split(","):
            doc = None
            d = re.search(r"\x00(\d+)\x00", item)
            if d:
                doc = docs[int(d.group(1))]
                item = item.replace(d.group(), " ")
            spec = " ".join(item.split())
            if not spec:
                continue
            sm = re.match(r"^(type\s+)?([\w$]+)(?:\s+as\s+([\w$]+))?$", spec)
            if not sm:
                raise ValueError("unrecognised export specifier: " + spec)
            local, name = sm.group(2), sm.group(3) or sm.group(2)
            is_type = type_only or bool(sm.group(1))
            if source is None and local in self.locals:
                decls = self.locals[local]
                kind = decls[0][0]
                self.add(name, kind, BUCKET[kind], doc, " ".join(t for _, t in decls))
            else:
                self.add(name, "reexport", "type" if is_type else "value", doc,
                         spec + (" from " + source.group(1) if source else ""))

    def exports(self):
        rows = []
        for (name, bucket), e in self.entries.items():
            since, stability = tags(e["doc"])
            rows.append({"name": name, "bucket": bucket, "kind": e["kind"], "since": since,
                         "stability": stability, "hash": _digest(e["parts"])})
        return sorted(rows, key=lambda r: (r["name"], r["bucket"]))


def build_snapshot(dts_files, version):
    """dts_files: {path relative to package/dist, e.g. 'http/HttpRouter.d.ts': text}."""
    modules, internal = {}, 0
    for rel in sorted(dts_files):
        parts = rel[:-len(".d.ts")].split("/")
        if "internal" in parts:
            internal += 1
            continue
        barrel = parts[-1] == "index"
        spec = "/".join(["effect"] + (parts[:-1] if barrel else parts))
        p = ModuleParser()
        try:
            p.parse(dts_files[rel])
        except ValueError as err:
            raise ValueError("%s: %s" % (rel, err)) from None
        modules[spec] = {"barrel": barrel, "exports": p.exports()}
    return {"package": "effect", "version": version, "schema": SCHEMA,
            "internal_files_excluded": internal, "modules": modules}


def dump_snapshot(snap):
    """Deterministic text: sorted keys, one export per line, no timestamps."""
    j = lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    head = ",\n".join(" %s: %s" % (j(k), j(snap[k])) for k in
                      ("internal_files_excluded", "package", "schema", "version"))
    mods = []
    for spec in sorted(snap["modules"]):
        m = snap["modules"][spec]
        rows = ",\n".join("    " + j(r) for r in m["exports"])
        mods.append('  %s: {\n   "barrel": %s,\n   "exports": [%s]}' % (
            j(spec), j(m["barrel"]), "\n" + rows + "\n   " if rows else ""))
    return "{\n%s,\n \"modules\": {\n%s\n }\n}\n" % (head, ",\n".join(mods))


# ------------------------------------------------------------------ snapshot cmd

def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def download(version):
    meta = json.loads(fetch("%s/effect/%s" % (REGISTRY, version)))
    data = fetch(meta["dist"]["tarball"])
    integrity = meta["dist"].get("integrity", "")
    if integrity.startswith("sha512-"):
        got = base64.b64encode(hashlib.sha512(data).digest()).decode()
        if got != integrity[len("sha512-"):]:
            raise ValueError("tarball integrity mismatch for effect@" + version)
    return data


def read_dts(tar_bytes):
    files = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile() and m.name.startswith("package/dist/") and m.name.endswith(".d.ts"):
                files[m.name[len("package/dist/"):]] = tf.extractfile(m).read().decode("utf-8")
    return files


def cmd_snapshot(args):
    if not VERSION_RE.match(args.version):
        print("not a version: " + args.version, file=sys.stderr)
        return 1
    try:
        data = Path(args.tarball).read_bytes() if args.tarball else download(args.version)
        snap = build_snapshot(read_dts(data), args.version)
    except (OSError, ValueError, KeyError, tarfile.TarError) as err:
        print("snapshot failed: %s" % err, file=sys.stderr)
        return 1
    out = Path(args.api_dir) / (args.version + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dump_snapshot(snap), encoding="utf-8")
    exports = sum(len(m["exports"]) for m in snap["modules"].values())
    print("wrote %s: %d modules, %d exports, %d internal files excluded"
          % (out, len(snap["modules"]), exports, snap["internal_files_excluded"]))
    return 0


# ---------------------------------------------------------------------- diff cmd

def module_tier(mod):
    """A module is unstable when it has exports and every one of them is tagged unstable."""
    tiers = {e["stability"] for e in mod["exports"]}
    return tiers.pop() if len(tiers) == 1 else "stable"


def _tier_order(tier):
    return (tier != "stable", tier)


def _count(n):
    return "%d export%s" % (n, "" if n == 1 else "s")


def collect_changes(a, b):
    """Every module and export difference between two snapshots, as a list of dicts.

    Each entry has `tier` (where `diff` files it), `section` (Modules added, Modules
    removed, Exports added, Exports removed or Exports changed), `line` (its `diff`
    text) and the structured fields `module`, `name`, `bucket`, `kind`, `old_tier`,
    `new_tier` and `detail`.  `diff` and `changes` both render from this one list.
    """
    out = []

    def put(tier, section, line, module, name=None, bucket=None, kind=None, old=None, new=None, detail=""):
        out.append({"tier": tier, "section": section, "line": line, "module": module, "name": name,
                    "bucket": bucket, "kind": kind, "old_tier": old, "new_tier": new, "detail": detail})

    ma, mb = a["modules"], b["modules"]
    for spec in sorted(set(ma) | set(mb)):
        if spec not in ma:
            t = module_tier(mb[spec])
            put(t, "Modules added", "`%s` (%d exports)" % (spec, len(mb[spec]["exports"])), spec,
                new=t, detail=_count(len(mb[spec]["exports"])))
        elif spec not in mb:
            t = module_tier(ma[spec])
            put(t, "Modules removed", "`%s` (%d exports)" % (spec, len(ma[spec]["exports"])), spec,
                old=t, detail=_count(len(ma[spec]["exports"])))
        else:
            ea = {(e["name"], e["bucket"]): e for e in ma[spec]["exports"]}
            eb = {(e["name"], e["bucket"]): e for e in mb[spec]["exports"]}
            for key in sorted(set(ea) | set(eb)):
                label = "`%s` `%s`%s" % (spec, key[0], " (type)" if key[1] == "type" else "")
                if key not in ea:
                    e = eb[key]
                    put(e["stability"], "Exports added", "%s (%s, since %s)" % (label, e["kind"], e["since"]),
                        spec, key[0], key[1], e["kind"], new=e["stability"])
                elif key not in eb:
                    e = ea[key]
                    put(e["stability"], "Exports removed", "%s (%s)" % (label, e["kind"]),
                        spec, key[0], key[1], e["kind"], old=e["stability"])
                else:
                    x, y = ea[key], eb[key]
                    why = []
                    if x["stability"] != y["stability"]:
                        why.append("tier %s -> %s" % (x["stability"], y["stability"]))
                    if x["since"] != y["since"]:
                        why.append("since %s -> %s" % (x["since"], y["since"]))
                    if x["hash"] != y["hash"]:
                        why.append("declaration changed")
                    if why:
                        put(y["stability"], "Exports changed", "%s: %s" % (label, ", ".join(why)),
                            spec, key[0], key[1], y["kind"], x["stability"], y["stability"], ", ".join(why))
    return out


def diff_snapshots(a, b):
    by_tier = {}
    for c in collect_changes(a, b):
        by_tier.setdefault(c["tier"], {}).setdefault(c["section"], []).append(c["line"])
    lines = ["# effect API changes: %s -> %s" % (a["version"], b["version"]), ""]
    if not by_tier:
        return "\n".join(lines + ["No changes.", ""])
    sections = ["Modules added", "Modules removed", "Exports added", "Exports removed", "Exports changed"]
    for tier in sorted(by_tier, key=_tier_order):
        lines += ["## %s" % tier, ""]
        for sec in sections:
            if sec in by_tier[tier]:
                lines += ["### %s" % sec, ""] + ["- " + s for s in by_tier[tier][sec]] + [""]
    return "\n".join(lines)


def load_snapshot(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_diff(args):
    try:
        a, b = load_snapshot(args.a), load_snapshot(args.b)
    except (OSError, ValueError) as err:
        print("diff failed: %s" % err, file=sys.stderr)
        return 1
    sys.stdout.write(diff_snapshots(a, b))
    return 0


# ------------------------------------------------------------------- changes cmd

def is_unstable_change(c):
    """True when either side of the change is tagged anything but stable."""
    return any(t not in (None, "stable") for t in (c["old_tier"], c["new_tier"]))


def _change_line(c):
    tier = c["new_tier"] if c["section"] == "Exports changed" else c["old_tier"]
    if c["name"] is None:
        return "- the whole module was removed (%s)" % c["detail"]
    head = "- `%s`%s [%s]" % (c["name"], " (type)" if c["bucket"] == "type" else "", tier)
    if c["section"] == "Exports removed":
        return "%s: removed (%s)" % (head, c["kind"])
    return "%s: changed, %s" % (head, c["detail"])


def render_changes(a, b, command=None):
    """The Markdown content of `reference/changes/<b version>.md`: what a release breaks.

    Lists removed and changed exports only.  Added exports break nobody, so they appear
    as a count.  The file is generated and carries no `verified` stamp.
    """
    cmd = command or "python3 tools/api-snapshot/api_snapshot.py changes <%s.json> <%s.json>" % (a["version"], b["version"])
    changes = collect_changes(a, b)
    added_mods = sum(1 for c in changes if c["section"] == "Modules added")
    added_exports = sum(1 for c in changes if c["section"] == "Exports added")
    breaking = [c for c in changes if c["section"] in ("Modules removed", "Exports removed", "Exports changed")]
    lines = [
        "# effect %s -> %s: what changed for exports that were not stable" % (a["version"], b["version"]),
        "",
        "> Generated by `%s`. Do not edit by hand." % cmd,
        "> It compares exactly two snapshots, `effect@%s` and `effect@%s`. Any release published between "
        "them is not listed on its own; its changes are folded into this file." % (a["version"], b["version"]),
        "> Tags in square brackets are the export's `@stability` tag (`stable` when untagged). "
        "A change is tagged by its old tag when it was removed, by its new tag when it changed.",
        "",
    ]
    groups = (
        ("Unstable and experimental exports", "removed or changed; anyone importing these should expect to follow them",
         [c for c in breaking if is_unstable_change(c)]),
        ("Stable exports removed or changed", "a break in a stable export is a semver break worth a closer look",
         [c for c in breaking if not is_unstable_change(c)]),
    )
    for title, why, rows in groups:
        lines += ["## %s" % title, "", why[0].upper() + why[1:] + ".", ""]
        if not rows:
            lines += ["None.", ""]
            continue
        for spec in sorted({c["module"] for c in rows}):
            lines += ["### `%s`" % spec, ""]
            lines += [_change_line(c) for c in rows if c["module"] == spec]
            lines.append("")
    lines += ["## Added", "",
              "%d export%s and %d module%s added; additions break nobody and are not listed. "
              "Run `api_snapshot.py diff` on the same two snapshots to list them."
              % (added_exports, "" if added_exports == 1 else "s", added_mods, "" if added_mods == 1 else "s"), ""]
    return "\n".join(lines)


def cmd_changes(args):
    try:
        a, b = load_snapshot(args.a), load_snapshot(args.b)
    except (OSError, ValueError) as err:
        print("changes failed: %s" % err, file=sys.stderr)
        return 1
    sys.stdout.write(render_changes(a, b))
    return 0


# ------------------------------------------------------------------------ watch cmd
#
# Compare the registry's `latest` `effect` with the newest committed snapshot.  When
# the registry is ahead, snapshot it, render the changes file against the previous
# newest snapshot, bump the plugin's PATCH version and prepend a changelog section.
# Every step is skipped when its result already exists, so a re-run changes nothing.

def semver_key(version):
    """Sort key: numeric core, and a release sorts after its own prereleases."""
    core, _, pre = version.partition("-")
    nums = tuple(int(x) for x in core.split("."))
    if not pre:
        return nums, (1,)
    return nums, (0,) + tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))


def snapshot_versions(api_dir):
    api_dir = Path(api_dir)
    found = [p.stem for p in api_dir.glob("*.json") if VERSION_RE.match(p.stem)] if api_dir.is_dir() else []
    return sorted(found, key=semver_key)


def registry_latest():
    return json.loads(fetch("%s/effect/latest" % REGISTRY))["version"]


PLUGIN_VERSION_RE = re.compile(r'("version"\s*:\s*")(\d+)\.(\d+)\.(\d+)(")')


def bump_plugin_patch(text):
    """(new text, new version): the first `"version"` in plugin.json with its PATCH + 1."""
    m = PLUGIN_VERSION_RE.search(text)
    if not m:
        raise ValueError("no semver \"version\" in the plugin manifest")
    new = "%s.%s.%d" % (m.group(2), m.group(3), int(m.group(4)) + 1)
    return text[:m.start()] + m.group(1) + new + m.group(5) + text[m.end():], new


def changelog_marker(version):
    return "Recorded the `effect@%s` release" % version


def add_changelog_section(text, plugin_version, effect_version, prev_version, changes_rel):
    """Insert `## <plugin_version>` below the preamble, above the newest existing section."""
    section = (
        "## %s\n\n- **%s.** The release watcher found it on npm's `latest` tag and generated "
        "`%s`, which lists what it removed or changed against `effect@%s`, unstable exports first. "
        "Reference chapters stamped with an older version should be read with that file.\n\n"
        % (plugin_version, changelog_marker(effect_version), changes_rel, prev_version))
    m = re.search(r"(?m)^## ", text)
    if not m:
        return text.rstrip("\n") + "\n\n" + section
    return text[:m.start()] + section + text[m.start():]


def cmd_watch(args):
    root = Path(args.repo_root)
    api_dir = Path(args.api_dir) if args.api_dir else root / "api" / "effect"
    changes_dir = Path(args.changes_dir) if args.changes_dir else root / "skills" / "effect-v4" / "reference" / "changes"
    manifest, changelog = root / ".claude-plugin" / "plugin.json", root / "CHANGELOG.md"
    try:
        latest = args.latest or registry_latest()
    except (OSError, ValueError, KeyError) as err:
        print("watch failed: cannot read the registry's latest effect: %s" % err, file=sys.stderr)
        return 1
    if not VERSION_RE.match(latest):
        print("watch failed: not a version: %s" % latest, file=sys.stderr)
        return 1
    if "-" in latest:
        print("nothing changed: the registry's latest is a prerelease (effect@%s); only releases are recorded" % latest)
        return 0
    have = snapshot_versions(api_dir)
    if not have:
        print("watch failed: no snapshot under %s to compare with" % api_dir, file=sys.stderr)
        return 1
    if semver_key(latest) < semver_key(have[-1]):
        print("nothing changed: the registry's latest (effect@%s) is older than the newest snapshot (%s)" % (latest, have[-1]))
        return 0
    older = [v for v in have if semver_key(v) < semver_key(latest)]
    snap_file, changes_file = api_dir / (latest + ".json"), changes_dir / (latest + ".md")
    if not older:
        print("nothing changed: effect@%s is the newest snapshot, and no earlier one exists to compare with" % latest)
        return 0
    prev = older[-1]
    try:
        changes_rel = changes_file.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        changes_rel = changes_file.name
    try:
        changelog_text = changelog.read_text(encoding="utf-8")
    except OSError as err:
        print("watch failed: %s" % err, file=sys.stderr)
        return 1
    need_bump = changelog_marker(latest) not in changelog_text
    if snap_file.is_file() and changes_file.is_file() and not need_bump:
        print("nothing changed: effect@%s is already recorded (snapshot, changes file and changelog)" % latest)
        return 0
    if not snap_file.is_file():
        rc = cmd_snapshot(argparse.Namespace(version=latest, api_dir=str(api_dir), tarball=args.tarball))
        if rc:
            return rc
    if not changes_file.is_file():
        try:
            a, b = load_snapshot(api_dir / (prev + ".json")), load_snapshot(snap_file)
        except (OSError, ValueError) as err:
            print("watch failed: %s" % err, file=sys.stderr)
            return 1
        changes_dir.mkdir(parents=True, exist_ok=True)
        cmd = "python3 tools/api-snapshot/api_snapshot.py watch"
        changes_file.write_text(render_changes(a, b, cmd), encoding="utf-8")
        print("wrote %s" % changes_file)
    if need_bump:
        try:
            text, new_version = bump_plugin_patch(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            print("watch failed: %s" % err, file=sys.stderr)
            return 1
        manifest.write_text(text, encoding="utf-8")
        changelog.write_text(add_changelog_section(changelog_text, new_version, latest, prev, changes_rel),
                             encoding="utf-8")
        print("plugin version -> %s; added a section to %s" % (new_version, changelog))
    print("recorded: %s" % latest)
    return 0


# --------------------------------------------------------------------- check cmd
#
# `Module.symbol` in a code span or fence is checked when `Module` is the last path
# segment of a recorded, non-barrel module.  Anything else (`console.log`, `foo.bar`)
# is ordinary code and is ignored.  Where several modules share the basename the
# symbol must exist in at least one.  Nested access checks the first two segments.

# Static members of JS globals whose names are also Effect modules: `Array.from` is
# the language's, so it is never reported even though effect/Array has no `from`.
JS_STATICS = {
    "Array": {"from", "of", "isArray", "fromAsync", "prototype"},
    "Number": {"isInteger", "isFinite", "isNaN", "isSafeInteger", "parseFloat", "parseInt", "MAX_SAFE_INTEGER",
               "MIN_SAFE_INTEGER", "MAX_VALUE", "MIN_VALUE", "EPSILON", "POSITIVE_INFINITY", "NEGATIVE_INFINITY",
               "NaN", "prototype"},
    "String": {"raw", "fromCharCode", "fromCodePoint", "prototype"},
    "BigInt": {"asIntN", "asUintN", "prototype"},
    "Boolean": {"prototype"},
    "Function": {"prototype"},
    "Symbol": {"iterator", "asyncIterator", "dispose", "asyncDispose", "for", "keyFor", "hasInstance", "toPrimitive", "toStringTag", "prototype"},
    "Error": {"captureStackTrace", "stackTraceLimit", "prototype"},
    "Date": {"now", "parse", "UTC", "prototype"},
    "Promise": {"all", "allSettled", "any", "race", "resolve", "reject", "withResolvers", "prototype"},
    "Object": {"keys", "values", "entries", "assign", "freeze", "fromEntries", "create", "defineProperty",
               "getPrototypeOf", "setPrototypeOf", "getOwnPropertyNames", "is", "prototype"},
    "Math": {"max", "min", "floor", "ceil", "round", "abs", "pow", "sqrt", "random", "trunc", "sign", "log", "PI"},
    "JSON": {"parse", "stringify"},
}
FILE_EXTENSIONS = {"ts", "tsx", "js", "mjs", "cjs", "json", "md", "d", "map"}
_QUALIFIED = re.compile(r"(?<![\w$./@\"'-])([A-Z][A-Za-z0-9_]*)\.([A-Za-z_$][\w$]*)")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SPAN = re.compile(r"(`+)(.+?)\1(?!`)", re.S)


def code_regions(text):
    """Yield (line number, code text) for every fenced block and inline span."""
    lines, i, prose = text.split("\n"), 0, []
    while i < len(lines):
        m = _FENCE.match(lines[i])
        if m:
            fence = m.group(1)
            j = i + 1
            close = re.compile(r"^ {0,3}%s{%d,}\s*$" % (re.escape(fence[0]), len(fence)))
            while j < len(lines) and not close.match(lines[j]):
                j += 1
            yield i + 2, "\n".join(lines[i + 1:j])
            i = j + 1
        else:
            prose.append((i + 1, lines[i]))
            i += 1
    blob = "\n".join(t for _, t in prose)
    numbers = [n for n, _ in prose]
    for m in _SPAN.finditer(blob):
        yield numbers[blob.count("\n", 0, m.start())], m.group(2)


def qualified_names(text):
    """Yield (line, module, symbol) for each `Module.symbol` in the chapter's code."""
    seen = set()
    for line0, code in code_regions(text):
        for m in _QUALIFIED.finditer(code):
            line = line0 + code.count("\n", 0, m.start())
            if (line, m.group(1), m.group(2)) not in seen:
                seen.add((line, m.group(1), m.group(2)))
                yield line, m.group(1), m.group(2)


def index_snapshot(snap):
    """basename -> [(specifier, set of top-level export names, has star re-export)]."""
    idx = {}
    for spec, mod in snap["modules"].items():
        if mod["barrel"]:
            continue
        names = {e["name"] for e in mod["exports"] if "." not in e["name"]}
        idx.setdefault(spec.rsplit("/", 1)[-1], []).append((spec, names, "*" in names))
    return idx


def check_chapter(path, text, load):
    """Return a list of failure messages for one chapter; `load(version)` gives its index or None."""
    first = text.split("\n", 1)[0].rstrip("\r")
    m = STAMP_RE.match(first)
    if not m:
        return ["%s: line 1 is not a stamp `<!-- verified: effect@<version> -->`" % path]
    version = m.group(1)
    idx = load(version)
    if idx is None:
        return ["%s: stamped effect@%s has no committed snapshot (api/effect/%s.json)" % (path, version, version)]
    failures = []
    for line, module, symbol in qualified_names(text):
        mods = idx.get(module)
        if not mods:
            continue
        if any(symbol in names or star for _, names, star in mods):
            continue
        if symbol in JS_STATICS.get(module, ()) or symbol in FILE_EXTENSIONS:
            continue
        failures.append("%s:%d: %s.%s is not an export of %s (effect@%s)"
                        % (path, line, module, symbol, " or ".join(sorted(s for s, _, _ in mods)), version))
    return failures


def cmd_check(args):
    chapters_dir, api_dir = Path(args.chapters_dir), Path(args.api_dir)
    chapters = sorted(p for p in chapters_dir.glob("*.md") if p.is_file()) if chapters_dir.is_dir() else []
    cache = {}

    def load(version):
        if version not in cache:
            f = api_dir / (version + ".json")
            cache[version] = index_snapshot(load_snapshot(f)) if f.is_file() else None
        return cache[version]

    failures = []
    for p in chapters:
        shown = p.resolve().relative_to(REPO_ROOT) if REPO_ROOT in p.resolve().parents else p
        failures += check_chapter(shown, p.read_text(encoding="utf-8"), load)
    print("checked %d chapter%s in %s" % (len(chapters), "" if len(chapters) == 1 else "s", chapters_dir))
    for f in failures:
        print(f, file=sys.stderr)
    return 1 if failures else 0


# ------------------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(
        prog="api_snapshot.py",
        description="Snapshot, diff and check the public API of the published `effect` package.",
        epilog="exit codes: 0 success; 1 problem found or command failed; 2 bad command line")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="write api/effect/<version>.json from the npm tarball (needs network)",
                       description="Download effect@<version> from the npm registry and write its snapshot. "
                                   "Deterministic: running it twice yields byte-identical files.")
    s.add_argument("version")
    s.add_argument("--api-dir", default=str(DEFAULT_API_DIR), help="where snapshots live (default: api/effect)")
    s.add_argument("--tarball", help="read this local .tgz instead of downloading (tests, offline)")
    s.set_defaults(fn=cmd_snapshot)
    d = sub.add_parser("diff", help="Markdown report of changes between two snapshots, by stability tier",
                       description="Print Markdown to stdout: modules and exports added, removed and changed, "
                                   "grouped by stability tier. Exits 0 whether or not anything changed.")
    d.add_argument("a")
    d.add_argument("b")
    d.set_defaults(fn=cmd_diff)
    g = sub.add_parser("changes", help="Markdown of what a release removed or changed (the reference/changes file)",
                       description="Print the generated breaking-changes file for two snapshots: removed and changed "
                                   "unstable/experimental exports by module, then removed or changed stable exports "
                                   "separately, then a count of additions. Names both versions; carries no verified stamp.")
    g.add_argument("a", help="the earlier snapshot")
    g.add_argument("b", help="the later snapshot")
    g.set_defaults(fn=cmd_changes)
    w = sub.add_parser("watch", help="record a new effect release if npm's latest is newer than the newest snapshot",
                       description="Compare the registry's `latest` effect with the newest snapshot under the api dir "
                                   "(by semver). Equal: print that nothing changed, touch nothing, exit 0. Newer: write "
                                   "its snapshot, write the changes file against the previous snapshot, bump the plugin's "
                                   "PATCH version and prepend a CHANGELOG section. Re-running changes nothing more. "
                                   "Follows `latest` only; a prerelease is never recorded.")
    w.add_argument("--repo-root", default=str(REPO_ROOT), help="repository root holding .claude-plugin and CHANGELOG.md")
    w.add_argument("--api-dir", help="default: <repo-root>/api/effect")
    w.add_argument("--changes-dir", help="default: <repo-root>/skills/effect-v4/reference/changes")
    w.add_argument("--latest", help="use this as the registry's latest version instead of asking npm (tests, offline)")
    w.add_argument("--tarball", help="read this local .tgz for the new version instead of downloading (tests, offline)")
    w.set_defaults(fn=cmd_watch)
    c = sub.add_parser("check", help="fail on chapters naming exports their stamped version lacks (offline)",
                       description="For each *.md directly in the chapters directory: read the stamp on line 1, "
                                   "load that version's snapshot, and fail naming file:line and Module.symbol for "
                                   "each unknown export of a known module. A missing stamp or snapshot also fails. "
                                   "Prints how many chapters it checked; zero chapters exits 0.")
    c.add_argument("--chapters-dir", default=str(DEFAULT_CHAPTERS_DIR),
                   help="default: skills/effect-v4/reference")
    c.add_argument("--api-dir", default=str(DEFAULT_API_DIR), help="default: api/effect")
    c.set_defaults(fn=cmd_check)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
