# framework-skills

Three reference skills for Claude Code, packaged as one plugin: two for Effect (one per major version) and one for SolidJS. All three are **model-invoked** — Claude reaches for them on its own when it recognises the framework, so you rarely type them.

| Skill | Covers | Scope boundary |
|---|---|---|
| `/frameworks:effect-v3` | Effect TS — `Effect<A, E, R>`, `Effect.gen`/pipe, typed errors, Context/Layer DI, Scope, fibers & structured concurrency, Ref/Queue/PubSub/STM, Schedule, Stream, Schema & Config, `@effect/platform`, `@effect/sql`, `@effect/rpc`, `@effect/vitest`, `@effect-atom` | **v3.x only** — selected by an installed `effect` 3.x; a project on `effect` 4.x uses `effect-v4` instead |
| `/frameworks:effect-v4` | Effect TS 4.x — resolves the installed `effect` version, sends you to the agent guide and examples that package ships, looks up an export's `@stability` tier before you rely on it, and holds four judgment chapters: coming from v3, working with unstable APIs, architecture, pitfalls | **4.x only** (4.0.0 or later) — selected by an installed `effect` 4.x; a 3.x install uses `effect-v3` instead. Not a migration guide from v3 |
| `/frameworks:solid` | SolidJS — signals/memos/effects, props reactivity, control flow, stores, resources & Suspense, context, refs & directives, `@solidjs/router`, `@tanstack/solid-query`, performance, testing, TypeScript | **v1.9.x client-side** — SSR/SolidStart and Solid 2.0 are out of scope |

Each skill is a router `SKILL.md` plus standalone `reference/NN-*.md` chapters. The router is small and always loaded; chapters are opened one at a time, only when the topic comes up — so a question about stores never pays for the streaming chapter.

**`effect-v3` and `solid` are references:** their chapters teach the API. **`effect-v4` is a router to the docs the installed package ships** (`AGENTS.md` and `ai-docs/` inside `node_modules/effect`) plus four chapters of judgment the package does not hold — it never restates the API, because an API fact read from anywhere but the installed version may be wrong for it. It also ships two dependency-free Node scripts (`scripts/version.mjs` resolves the installed version, `scripts/stability.mjs` looks up an export's stability tier) and a generated `reference/changes/` directory recording what each new `effect` release removed or changed.

### Choosing between the two Effect skills

The installed `effect` major decides. The `effect-v4` skill resolves the version first, from the file being edited, and hands a 3.x install to `effect-v3`; the `effect-v3` skill says the same in the other direction. They are not meant to be mixed: v3 and v4 idioms differ, and nothing in `effect-v3` describes v4.

To **upgrade** a codebase from v3 to v4, neither skill is the tool: this plugin does not teach migration. Effect maintains its own `effect-v3-to-v4` skill in [`Effect-TS/skills`](https://github.com/Effect-TS/skills) (`skills/effect-v3-to-v4`).

---

## Install

```
/plugin marketplace add trinity-ai-labs/claude-plugins
/plugin install frameworks@trinity-ai-labs
```

Then enable auto-update: `/plugin` → **Marketplaces** → `trinity-ai-labs` → **Enable auto-update**. It is off by default for third-party marketplaces.

⚠️ Updates land on a **version bump**, not on a push. `plugin.json` declares `version`, so an install is pinned to that string — CI fails a change reaching `main` if skills change without bumping it, so this can't happen silently (a pull request into any other base is not held to the bump). See [CHANGELOG.md](CHANGELOG.md).

**To develop these skills**, clone into your skills directory instead — edits then apply live, no release step:

```bash
git clone https://github.com/trinity-ai-labs/framework-skills ~/.claude/skills/frameworks
```

Before opening a pull request, run the same content checks CI runs, from any directory in the clone (needs only bash and Python 3):

```bash
bash scripts/check.sh
```

It checks, in order: every skill's frontmatter `name` matches its directory; no product name or home-directory path appears in any text file under `skills/`; every `## Contents` link in a chapter resolves; the API snapshot tool's own tests pass; and every `effect-v4` chapter names only exports its stamped version has.

**Contributing to `effect-v4`.** A chapter under `skills/effect-v4/reference/` opens with a stamp as its first line, `<!-- verified: effect@<version> -->`, and names only exports in that version's committed snapshot (`api/effect/<version>.json`). In code spans and fences, a `Module.symbol` that the stamped version does not export fails `python3 tools/api-snapshot/api_snapshot.py check` (which `scripts/check.sh` runs): an API v4 removed is written in prose or unqualified, never as `Module.symbol`. [`tools/api-snapshot/README.md`](tools/api-snapshot/README.md) has the exact rules. Do not edit `reference/changes/*.md` by hand; the tool generates them.

**The release watcher.** `.github/workflows/effect-release-watch.yml` runs daily and, when npm's `latest` `effect` is newer than the newest snapshot, opens a pull request per release carrying the snapshot, the generated changes file, a patch version bump and a changelog section. It needs the repository setting **Allow GitHub Actions to create and approve pull requests** (Settings → Actions → General). Read the changes file before merging: a removed or changed stable export is a semver break.

---

## Using them

You normally don't invoke these — Claude does, based on the frontmatter `description`. Ask it to fix a Solid list that loses input focus on every keystroke, or an Effect `R` channel that won't resolve, and the relevant skill loads itself.

To force one, name it: `/frameworks:solid`, `/frameworks:effect-v3` or `/frameworks:effect-v4`.

When dispatching sub-agents, name the skill as an explicit first step — a sub-agent won't reach for it on its own as reliably as the main thread does:

> Step 0: invoke the `frameworks:solid` skill.

---

## What "the reference app" means

Several chapters ground a pattern in how a real application does it — those say **the reference app**. It's a production Tauri desktop application: SolidJS UI, an Effect service layer, Solid Query for server state. The examples are real rather than invented, which is what makes the pitfalls chapters worth reading, but nothing in here is specific to it — every pattern stands alone.

---

## Layout

```
.
├── .claude-plugin/plugin.json
├── .github/workflows/
│   ├── ci.yml                   # runs scripts/check.sh · version bump (changes reaching main)
│   └── effect-release-watch.yml # daily: opens a PR per new effect release
├── api/effect/<version>.json    # committed snapshot of one effect release's exports
├── scripts/check.sh             # frontmatter · identifier sweep · TOC links · tool tests · chapter symbols
├── tools/api-snapshot/          # snapshot · diff · changes · watch · check (Python 3, stdlib only)
└── skills/
    ├── effect-v3/
    │   ├── SKILL.md             # the router
    │   └── reference/NN-*.md    # 18 chapters
    ├── effect-v4/
    │   ├── SKILL.md             # the router: resolve version, read the bundled guide, look up stability
    │   ├── scripts/             # version.mjs · stability.mjs
    │   └── reference/
    │       ├── NN-*.md          # 4 chapters
    │       └── changes/         # generated: what each effect release removed or changed
    └── solid/
        ├── SKILL.md
        └── reference/NN-*.md    # 16 chapters
```

---

## License

MIT — see [LICENSE](LICENSE).
