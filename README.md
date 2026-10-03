# framework-skills

Two deep, source-verified reference skills for Claude Code, packaged as one plugin. Both are **model-invoked** — Claude reaches for them on its own when it recognises the framework, so you rarely type them.

| Skill | Covers | Scope boundary |
|---|---|---|
| `/frameworks:effect-v3` | Effect TS — `Effect<A, E, R>`, `Effect.gen`/pipe, typed errors, Context/Layer DI, Scope, fibers & structured concurrency, Ref/Queue/PubSub/STM, Schedule, Stream, Schema & Config, `@effect/platform`, `@effect/sql`, `@effect/rpc`, `@effect/vitest`, `@effect-atom` | **v3.x only** — v4 is out of scope |
| `/frameworks:solid` | SolidJS — signals/memos/effects, props reactivity, control flow, stores, resources & Suspense, context, refs & directives, `@solidjs/router`, `@tanstack/solid-query`, performance, testing, TypeScript | **v1.9.x client-side** — SSR/SolidStart and Solid 2.0 are out of scope |

Each skill is a router `SKILL.md` plus standalone `reference/NN-*.md` chapters. The router is small and always loaded; chapters are opened one at a time, only when the topic comes up — so a question about stores never pays for the streaming chapter.

---

## Install

```
/plugin marketplace add trinity-ai-labs/claude-plugins
/plugin install frameworks@trinity-ai-labs
```

Then enable auto-update: `/plugin` → **Marketplaces** → `trinity-ai-labs` → **Enable auto-update**. It is off by default for third-party marketplaces.

⚠️ Updates land on a **version bump**, not on a push. `plugin.json` declares `version`, so an install is pinned to that string — CI fails the build if skills change without bumping it, so this can't happen silently. See [CHANGELOG.md](CHANGELOG.md).

**To develop these skills**, clone into your skills directory instead — edits then apply live, no release step:

```bash
git clone https://github.com/trinity-ai-labs/framework-skills ~/.claude/skills/frameworks
```

Before opening a pull request, run the same content checks CI runs, from any directory in the clone (needs only bash and Python 3):

```bash
bash scripts/check.sh
```

---

## Using them

You normally don't invoke these — Claude does, based on the frontmatter `description`. Ask it to fix a Solid list that loses input focus on every keystroke, or an Effect `R` channel that won't resolve, and the relevant skill loads itself.

To force one, name it: `/frameworks:solid` or `/frameworks:effect-v3`.

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
├── .github/workflows/ci.yml     # runs scripts/check.sh · version bump (changes reaching main)
├── scripts/check.sh             # frontmatter · identifier sweep · TOC links
└── skills/
    ├── effect-v3/
    │   ├── SKILL.md             # the router
    │   └── reference/NN-*.md    # 18 chapters
    └── solid/
        ├── SKILL.md
        └── reference/NN-*.md    # 16 chapters
```

---

## License

MIT — see [LICENSE](LICENSE).
