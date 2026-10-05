# Changelog

Versions are the `version` field in `.claude-plugin/plugin.json`. Because that field is set, an installed plugin only picks up changes when it **changes** — pushing to `main` alone ships nothing. CI enforces the bump for a change reaching `main`; a pull request into any other branch is not held to it.

## 1.1.1

- **Recorded the `effect@4.0.1` release.** The release watcher found it on npm's `latest` tag and generated `skills/effect-v4/reference/changes/4.0.1.md`, which lists what it removed or changed against `effect@4.0.0`, unstable exports first. Reference chapters stamped with an older version should be read with that file.

## 1.1.0

- **New skill: `effect-v4`** (`/frameworks:effect-v4`) for projects on `effect` 4.x. It is a router, not an API reference: it resolves the installed `effect` version from the file being edited (`scripts/version.mjs`), sends you to the `AGENTS.md` and `ai-docs/` the installed package ships, and looks up an export's `@stability` tier before you rely on it (`scripts/stability.mjs`). Four chapters hold what the package's docs do not: coming from v3, working with unstable APIs, architecture, and recurring pitfalls. Each is stamped with the `effect` release it was checked against, and `reference/changes/` records what each later release removed or changed.
- **The chapters follow the published `effect@4.0.0` package where upstream's migration guides differ from it.** The process keep-alive happens only under `runMain` (`Effect.runFork(Effect.never)` exits at once); `Option` and `Result` are not yieldable in `Effect.gen`, so `Effect.fromOption` and `Effect.fromResult` bridge them; and one layer-memoization example's comment does not match measured behaviour, so the chapters carry measured tables instead.
- **`effect-v3` and `effect-v4` are chosen by the installed `effect` major.** `effect-v3` now routes a 4.x project to `effect-v4`, and says v4 is the current stable major rather than a beta; its description no longer says v4 is out of scope. A 3.x install is handed from `effect-v4` to `effect-v3`. Neither teaches migration: upgrading a codebase is Effect's own `effect-v3-to-v4` skill (`Effect-TS/skills`).
- **API snapshot tool and a symbol check on the chapters.** `tools/api-snapshot/` records what a published `effect` release exports, and at which stability, in `api/effect/<version>.json` (`4.0.0` is committed). A chapter must open with `<!-- verified: effect@<version> -->` and may name only exports that version has; the check fails naming file, line and symbol.
- **Release watcher.** `.github/workflows/effect-release-watch.yml` runs daily and opens a pull request per new `effect` release: the snapshot, a generated changes file, a patch bump of this plugin and a changelog section. It needs the repository setting "Allow GitHub Actions to create and approve pull requests".
- **`scripts/check.sh` is the one local check** (`bash scripts/check.sh`), the same checks CI runs. Its identifier sweep now reads every text file under `skills/`, scripts included, not only Markdown.
- **The version bump is owed only by a change reaching `main`.** A pull request into another base is no longer held to it.

## 1.0.1

- **Install now points at `trinity-ai-labs/claude-plugins`.** The marketplace catalogue used to live inside `orchestration-skills`, so installing these skills meant adding an unrelated plugin's repo as a marketplace first. The catalogue moved to a repo that ships no plugin of its own. The marketplace *name* is unchanged, so `frameworks@trinity-ai-labs` still resolves — only the `marketplace add` line moves.

## 1.0.0

First release. The `effect-v3` and `solid` reference skills, previously two separate repos installed by shell script, packaged as one plugin.

- De-identified: examples that were grounded in a specific product now say **the reference app**, including the code identifiers and source paths that named it even after the prose was generic.
- Every reference chapter over 300 lines gained a `## Contents` index, so a chapter can be scanned before it is read in full.
