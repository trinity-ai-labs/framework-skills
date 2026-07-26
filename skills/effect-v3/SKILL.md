---
name: effect-v3
description: >-
  Use when writing, reading, debugging, or structuring TypeScript that uses Effect (Effect TS, the
  `effect` library) or its ecosystem — Effect<A, E, R>, Effect.gen / pipe, typed errors
  (Data.TaggedError, catchTag), dependency injection (Context, Tag, Effect.Service, Layer), Scope &
  resource management, fibers & structured concurrency, Ref/Queue/PubSub/STM, Schedule/retry,
  Stream/Sink, Schema & Config, logging/metrics/tracing, @effect/platform (HttpApi, HttpClient,
  runMain), @effect/sql, @effect/rpc, workers, @effect/vitest testing, @effect-atom reactive state —
  and when an `R`/`E` type won't resolve, learning an API, picking the idiomatic approach, or laying
  out an Effect codebase. Covers Effect v3.x only; Effect v4 is out of scope.
---

# Effect v3 — the bible

A thorough, source-verified reference for the **Effect v3 line** (the `effect` library) and its ecosystem — verified against **`effect@3.22.0`**, the current stable release. Every API here was checked against the actual source, backstopped by the official docs and best-practice research.

**How to use this skill:** this file is the router. Read the short *mental model* and *how to think* sections below to orient, then open the one `reference/NN-*.md` file for the topic at hand — each is a deep, standalone chapter. Don't load them all; load the one you need.

> **v3 only.** Effect v4 exists as a public beta (npm `beta` tag) and is a rewrite with different semantics and a unified package versioning scheme. Nothing here describes v4 — do not mix v4 idioms into a v3 codebase. Check what the project actually depends on before writing code.

---

## The 30-second mental model

Everything is `Effect<A, E, R>`: a **lazy, immutable description** of a program that, when run, either succeeds with `A`, fails with a typed error `E`, or needs services `R` provided first.

- It's a *value*, not a running computation — building one has no side effects. You run it once, at the edge (`runMain`/`runPromise`).
- Errors live in the **type** (`E`), as named tagged values — not `throw`.
- Dependencies live in the **type** (`R`) — and providing them (via `Layer`) removes them, until `R = never` means "fully wired, runnable."
- Two authoring styles: `Effect.gen(function* () { const x = yield* eff })` (sequential/branching — primary) and `.pipe(Effect.map(...), Effect.flatMap(...))` (data-last composition). Mix freely.

```ts
import { Effect, Data } from "effect"

class UserNotFound extends Data.TaggedError("UserNotFound")<{ id: string }> {}

const getName = (id: string): Effect.Effect<string, UserNotFound, UserRepo> =>
  Effect.gen(function* () {
    const repo = yield* UserRepo               // R: needs UserRepo
    const user = yield* repo.findById(id)      // E: may fail UserNotFound
    return user.name                            // A: succeeds with string
  })

// at the edge: provide deps (R → never), handle errors, run once
getName("u1").pipe(
  Effect.catchTag("UserNotFound", () => Effect.succeed("anonymous")),
  Effect.provide(UserRepo.Default),
  Effect.runPromise
)
```

---

## How to think in Effect

1. **Build descriptions everywhere; run at the edge.** One `runMain`/`ManagedRuntime` per entry point. Never nest `runSync`/`runPromise` inside logic.
2. **A service is a deep module.** A `Tag` + interface is the simple surface; its `Layer` hides the complexity. Design the interface deliberately, delegate the implementation. → [Architecture](reference/16-architecture.md)
3. **The layer graph is your architecture.** Dependencies are typed values composed with `Layer.provide`/`merge`, built once (memoized), swappable at any node. → [Context, Services & Layers](reference/05-context-layers.md)
4. **Errors are domain vocabulary.** Model expected failures as `Data.TaggedError` named in the domain's language; let bugs be defects (`die`). → [Error management](reference/04-errors.md)
5. **Reach for the stdlib before hand-rolling.** Retries, concurrency, debounce, mutexes, state, cleanup, config — Effect already has the primitive. → [Pitfalls](reference/17-pitfalls.md)

---

## Reference index — open the chapter you need

### Foundations
| Read this when you need… | File |
| --- | --- |
| What `A/E/R` mean, laziness, gen vs pipe, why Effect | [`01-mental-model.md`](reference/01-mental-model.md) |
| Constructors (`succeed`/`sync`/`tryPromise`/`async`…) and running (`runPromise`/`runFork`/`ManagedRuntime`) | [`02-creating-running.md`](reference/02-creating-running.md) |
| `map`/`flatMap`/`all`/`forEach`, Do-notation, control flow | [`03-combinators.md`](reference/03-combinators.md) |

### Errors & dependencies
| Read this when you need… | File |
| --- | --- |
| Typed errors, `Data.TaggedError`, `catchTag`/`catchAll`, `Cause`/`Exit`, accumulation | [`04-errors.md`](reference/04-errors.md) |
| **Dependency injection: `Context`, `Tag`, `Effect.Service`, `Layer`, wiring an app** (keystone) | [`05-context-layers.md`](reference/05-context-layers.md) |

### Resources, concurrency, time
| Read this when you need… | File |
| --- | --- |
| `Scope`, `acquireRelease`, finalizers, scoped layers | [`06-resources-scope.md`](reference/06-resources-scope.md) |
| Fibers, structured concurrency, `fork`/`race`/`timeout`, interruption | [`07-concurrency-fibers.md`](reference/07-concurrency-fibers.md) |
| `Ref`/`SynchronizedRef`/`SubscriptionRef`/`FiberRef`, `Deferred`, `Queue`, `PubSub`, `Semaphore`, STM | [`08-state-coordination.md`](reference/08-state-coordination.md) |
| `Schedule`, `retry`/`repeat` (incl. retry budgets), `Duration`, `Clock`, `Cron`, caching, rate limiting | [`09-scheduling-time.md`](reference/09-scheduling-time.md) |

### Data, streams, schema
| Read this when you need… | File |
| --- | --- |
| `Stream`/`Sink`/`Channel` — pull-based, back-pressured pipelines | [`10-streams.md`](reference/10-streams.md) |
| `Schema` (decode/encode/transform/class) and `Config` (typed configuration/secrets) | [`11-schema.md`](reference/11-schema.md) |
| `Option`/`Either`, `Data`, `Match`, `Equal`/`Brand`, `Chunk`/`HashMap`, functional `Array`/`Record` | [`12-data-pattern-matching.md`](reference/12-data-pattern-matching.md) |

### Application
| Read this when you need… | File |
| --- | --- |
| Logging, metrics, tracing/spans, `@effect/opentelemetry` | [`13-observability.md`](reference/13-observability.md) |
| `@effect/platform`: HttpApi, HttpClient, FileSystem, `runMain` + graceful shutdown, CLI — **and the adjacent packages `@effect/sql`, `@effect/rpc`, workers** | [`14-platform.md`](reference/14-platform.md) |
| Testing with `@effect/vitest`, `it.effect`, `TestClock`, test layers | [`15-testing.md`](reference/15-testing.md) |

### Cross-cutting & ecosystem
| Read this when you need… | File |
| --- | --- |
| **How to organize an Effect codebase** — services as deep modules, the layer graph, the edge, adopting Effect incrementally, project setup (tsconfig, language-service plugin) | [`16-architecture.md`](reference/16-architecture.md) |
| Anti-patterns & gotchas (sequential `all`, lazy effects, nested runs, defects, timers…) + **diagnosing an `E`/`R` type error** | [`17-pitfalls.md`](reference/17-pitfalls.md) |
| `@effect-atom` — reactive state for Effect in React/Solid/Vue (ecosystem add-on) | [`18-effect-atom.md`](reference/18-effect-atom.md) |

### Questions that span two chapters

Some common asks don't live in one file. Open both:

| Question | Chapters |
| --- | --- |
| Where should this state live — `Ref` vs `SubscriptionRef` vs an `Atom`? | [`08`](reference/08-state-coordination.md) (the primitives) + [`18`](reference/18-effect-atom.md) (the UI-facing one) |
| Retry this, but only on one tagged error | [`09`](reference/09-scheduling-time.md) (`Schedule`, budgets) + [`04`](reference/04-errors.md) (which tag, `tapErrorTag`) |
| Swap a real service for a fake in a test | [`15`](reference/15-testing.md) (the runner) + [`05`](reference/05-context-layers.md) (why `.Default` may ignore your fake) |
| Adopt Effect in a codebase that isn't Effect yet | [`16`](reference/16-architecture.md) (the boundary + migration path) + [`02`](reference/02-creating-running.md) (`ManagedRuntime`, wrapping Promises) |

---

## Conventions in these docs

- Code targets the **Effect v3 line**, verified against `effect@3.22.0` and the ecosystem packages released against it (`@effect/platform` 0.97.x, `@effect/vitest` 0.30.x, `@effect/sql` 0.52.x, `@effect/rpc` 0.76.x — the first-party packages release in lockstep and each pins `effect@^3.22.0`). All examples use real imports (`import { Effect, Layer, Schema } from "effect"`).
- `Effect.gen` is shown as the primary style; `.pipe` equivalents appear where they teach something.
- `❌ don't / ✅ do` pairs flag the idiomatic choice.
- `Schema` lives in the **core `effect` package** in v3 (`import { Schema } from "effect"`) — *not* the legacy `@effect/schema`.
- `@effect-atom` is a separate ecosystem library (`@effect-atom/atom-*`), not part of core Effect.

## Verifying against source

When in doubt about an API, the source of truth is the Effect repo — `Effect-TS/effect`, **branch `v3`**. Grep the package source, e.g. `rg "export const retry" packages/effect/src/Effect.ts`. A local clone lives at `~/Code/Ozner/effect` when present.

⚠️ **`main` is the v4 development branch.** Grepping `main` (or pulling a clone that tracks it) gives you v4 APIs that don't exist in v3 — check out `v3` or the `effect@3.x` tag first, and treat a clone whose `packages/effect/package.json` reads `4.0.0-*` as the wrong tree for this skill. <https://effect.website/docs> still documents v3.

Never guess an API name; confirm it exists.
