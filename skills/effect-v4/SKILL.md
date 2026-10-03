---
name: effect-v4
description: >-
  Use when writing, reading, debugging, or structuring TypeScript that uses Effect (Effect TS, the
  `effect` library) in a project whose installed `effect` is 4.x (4.0.0 or later). Resolves the installed
  version first, sends you to the agent guide and examples that package ships, and looks up an export's
  `@stability` tier before you rely on it (unstable and experimental APIs can break in minor and patch
  releases). The installed major selects the skill: a 3.x install uses the `effect-v3` skill instead, so
  stop here and hand off to it. Not a migration guide from v3.
---

# Effect v4 — a router, not a reference

This skill does not restate Effect's API. An Effect 4.x package ships its own guide and runnable examples, matched to the exact version installed, and an API fact read from anywhere else may be wrong for that version. The skill's job is to get you to those docs, to tell you how stable an export is before you build on it, and to hold the few judgment calls the docs do not.

**Two scripts ship with this skill, in `scripts/` beside this file.** A skill is installed somewhere your project is not, so run them by path: below, `<skill-dir>` is the directory this `SKILL.md` is in. Both are dependency-free Node (18+) and run from your project; neither needs a build or an install.

---

## The steps, in order

### 1. Resolve the installed `effect` version, from the file you are editing

```sh
node <skill-dir>/scripts/version.mjs <directory of the file you are editing>
```

It prints the version alone on stdout (for example `4.0.0`) and says on stderr where it found it. It walks up through every `node_modules` as Node does, so in a monorepo each package gets its own answer: resolve per package, never once for the repository.

- **A `3.x` result: stop and use the `effect-v3` skill.** Nothing below applies to a 3.x install, and v3 and v4 idioms must not be mixed.
- **Nothing installed:** it falls back to the version a lockfile pins (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, text `bun.lock`) and says so; install dependencies to confirm. A binary `bun.lockb` it cannot read, and it says that too. It exits non-zero with a message when no version resolves; then read the `effect` range in the nearest `package.json`, and ask before guessing a major.

### 2. Read the bundled guide: it is the source for API facts

The installed package carries, at its root, `AGENTS.md` (the entry point; `CLAUDE.md` is an identical copy) and `ai-docs/` (examples organised by topic that `AGENTS.md` links to), plus `src/` and `dist/`. Open them in the package this project resolves, which is `node_modules/effect` in the directory step 1 named, or the nearest one above it.

Read `AGENTS.md` first, then only the `ai-docs/` examples for the topic at hand. Prefer these and the package's own source to memory, to older blog posts, and to anything written for 3.x.

**If the package is not installed** (so there is no copy to read), the same material is in the upstream repository `Effect-TS/effect` at the release tag `effect@<version>`, using the version from step 1: `ai-docs/` at the repository root, and `LLMS.md`, which is the file the package's `AGENTS.md` is generated from. The repository has no `AGENTS.md` of its own.

### 3. Look up stability before you rely on an export

```sh
node <skill-dir>/scripts/stability.mjs <module> <export> [--from <directory>]
```

`<module>` is the import specifier and `<export>` the name exported from it. `--from` is where to resolve `effect` from (default: the current directory; pass the directory from step 1 in a monorepo). It prints `stable`, `unstable` or `experimental`, read from the `@stability` tag on that export in the installed type definitions, and exits non-zero with a message for a module or export that does not exist or an install that is not 4.x.

**Run it for every export you have not already looked up, and especially for anything outside the core root modules or that exposes a third-party dependency.** Stability is a property of the export, not of the module or the import path: a stable module can hold unstable exports, and a group can mix stable and unstable modules. Do not infer a tier from a module's name or from a list, and do not carry one over from another version; look it up.

What the tiers mean is upstream's policy (Effect-TS/effect `MIGRATION.md`): an untagged export follows strict semver; `unstable` may receive breaking changes in minor releases; `experimental` may receive breaking changes across patch versions. So: pin the exact version for what you build on an `unstable` or `experimental` export, isolate its use behind a small module of your own, and tell the person you are working for that you used one.

As a version-stamped hint only, never the complete set: in 4.0.0 the modules of the groups imported as `effect/ai`, `cli`, `cluster`, `devtools`, `eventlog`, `http`, `http-api`, `net`, `observability`, `persistence`, `process`, `reactivity`, `rpc`, `schema`, `socket`, `sql`, `workers` and `workflow` are tagged `unstable`; `effect/encoding` and `effect/testing` mix both; and unstable exports also sit in otherwise stable root modules. Only the script answers for an export.

### 4. Open an authored chapter only for a judgment question

The chapters carry judgment the bundled docs do not: what changes for a reader with v3 habits, stability discipline, architecture, pitfalls. They never restate an API. Open one only when the question is "which approach" or "what goes wrong", not "what is the signature".

| Read this when you need… | File |
| --- | --- |
| What a reader with v3 habits gets wrong in v4 | [`01-coming-from-v3.md`](reference/01-coming-from-v3.md) |
| How to work with unstable and experimental APIs | [`02-stability.md`](reference/02-stability.md) |
| How to lay out an Effect 4 codebase | [`03-architecture.md`](reference/03-architecture.md) |
| The mistakes that recur, and what to do instead | [`04-pitfalls.md`](reference/04-pitfalls.md) |

To port an existing v3 codebase to v4, this skill is not the tool: Effect maintains a migration skill, `effect-v3-to-v4` in `Effect-TS/skills`.

### 5. Check for version drift before you trust a chapter

Each chapter's first line is `<!-- verified: effect@<version> -->`, the release it was checked against. When the installed version (step 1) is newer than a chapter's stamp, open `reference/changes/<version>.md` for each release after the stamp up to and including the installed one, and read what changed before relying on the chapter. Where a release has no file there, say so and trust the installed docs from step 2 over the chapter.

---

## Reference index

| Path | What it is |
| --- | --- |
| `reference/01-coming-from-v3.md` | Orientation for a reader with v3 habits |
| `reference/02-stability.md` | Working with the stability tiers |
| `reference/03-architecture.md` | Laying out an Effect 4 codebase |
| `reference/04-pitfalls.md` | Recurring mistakes |
| `reference/changes/<version>.md` | What changed in one release, by stability tier |
| `scripts/version.mjs` | Step 1 |
| `scripts/stability.mjs` | Step 3 |
