# api-snapshot

Records what the published `effect` package exports and at which stability, and
rejects a chapter that names an export its stamped version does not have.
Python 3.9 or later, standard library only. Run it as `python3 tools/api-snapshot/api_snapshot.py <command>`.

| Command | Does | Network |
|---|---|---|
| `snapshot <version>` | Downloads `effect@<version>` from the npm registry (integrity-checked) and writes `api/effect/<version>.json`. Deterministic: sorted, no timestamps, so two runs are byte-identical and release diffs read in git. | yes |
| `diff <a.json> <b.json>` | Markdown on stdout: modules and exports added, removed and changed, grouped by stability tier (`stable` first). | no |
| `changes <a.json> <b.json>` | Markdown on stdout: the content of a `skills/effect-v4/reference/changes/<version>.md` file. Removed and changed exports tagged anything but `stable`, grouped by module; then removed or changed stable exports in their own section (a semver break); then a count of additions (they break nobody, so they are not listed; use `diff` for them). Names both versions, says it is generated, and carries no `verified` stamp. | no |
| `watch` | The release watcher: compares the registry's `latest` `effect` with the newest `api/effect/*.json` (by semver). Equal and already recorded: prints that nothing changed and touches nothing. Newer: writes its snapshot, writes the changes file against the previous snapshot, bumps the PATCH version in `.claude-plugin/plugin.json` and prepends a `## <version>` section to `CHANGELOG.md`. Each step is skipped when its result already exists, so re-running is safe (an existing changes file is never overwritten; delete it to regenerate). Follows `latest` only, never a prerelease. | yes (the registry, and the tarball unless `--tarball`) |
| `check` | For each `*.md` directly in `skills/effect-v4/reference/`: reads the stamp on line 1, loads that version's snapshot, and fails naming `file:line` and `Module.symbol` for each unknown export. Prints how many chapters it checked; none is exit 0. | no |

Exit codes: `0` success; `1` a problem found (check failures, download or parse error); `2` bad command line.
`check` takes `--chapters-dir` and `--api-dir`; `snapshot` takes `--api-dir` and `--tarball <file>` (offline).
`watch` takes `--repo-root` (it reads and writes `api/effect/`, the changes directory, `.claude-plugin/plugin.json` and `CHANGELOG.md` under it), `--latest <version>` (skip the registry lookup) and
`--tarball <file>`, so its whole path runs offline in tests. It ends with a `recorded: <version>` line when it
changed something. `.github/workflows/effect-release-watch.yml` runs it daily and opens the pull request.
The JSON layout is private; drive the tool through the command line.

## What is recorded

- A **module** is a `.d.ts` under `dist/` with no `internal` path segment, named by its import specifier
  (`effect/Effect`, `effect/http/HttpRouter`). Internal files are counted, not recorded.
- **Barrels** (`index.d.ts`: `effect`, `effect/http`, ...) are recorded as modules flagged `barrel`; their
  `export * as X` lines are exports of kind `module`. Barrels are skipped by `check`.
- An **export** is identified by module + name + bucket (`value`, `type` or `namespace`), so an interface and a
  const sharing a name stay distinct. Overloads are one export; `export { x_ as x }` records `x`; helpers such as
  `Foo_base` are not exports. Each carries `kind`, `since`, `stability` and a hash of its comment-stripped declaration.
- **Namespace members** are recorded as `Namespace.member` (they have their own `@since` and tier).
- **Stability** is the export's own `@stability` tag, `stable` when untagged. Nothing is inherited from a module header.
- A module's tier in `diff` is `unstable` only when every export of it is.

## How `check` reads a chapter

Line 1 must be exactly `<!-- verified: effect@<version> -->`. In code spans and fences, `Module.symbol` is
checked only when `Module` is the last path segment of a recorded non-barrel module (case-sensitive); anything else
(`console.log`, `foo.bar`) is ignored. If several modules share the basename, the symbol must exist in one of
them. Only the first two segments of `A.B.C` are checked. Static members of JS globals that share a module name
(`Array.from`, `Number.isInteger`) and file names (`Schema.ts`) are not reported. Prose outside code is not checked.

Tests: `python3 -m unittest discover -s tools/api-snapshot/tests` (fixtures live in `tests/fixtures/`).
