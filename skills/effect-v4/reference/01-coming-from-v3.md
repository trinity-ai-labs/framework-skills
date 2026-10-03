<!-- verified: effect@4.0.0 -->
# Coming from v3: the habits to drop

> **When you reach for this:** you know Effect 3 well, you are about to write or read Effect 4 code, and your hands keep typing something that no longer exists or no longer means what it did. This chapter names the shifts that change a habit and says where the authoritative per-symbol answer lives. It is orientation, not a rename table, and it is not a migration guide: to port a codebase, use Effect's own `effect-v3-to-v4` skill (in `Effect-TS/skills`) and the guides listed below.

The programming model did not change. `Effect<A, E, R>`, `Layer`, `Schema`, `Stream` and `Effect.gen` are what you know. What changed is how packages are laid out, how services are declared, a handful of renamed families, and a few places where v3 behaviour was an accident that v4 removed. Each shift below is **what it was, what it is now, the habit to drop, and the upstream guide it traces to**.

Everything here was checked against the published `effect@4.0.0`, not only against upstream's guides. In three places the package and the guide disagree (the process keep-alive, what `yield*` accepts, and one layer-isolation example). Those are called out where they occur, and where they disagree the installed package wins.

## Contents

- [Where the per-symbol answer lives](#where-the-per-symbol-answer-lives)
- [1. One package, one version](#1-one-package-one-version)
- [2. Services: Tag classes become Context.Service](#2-services-tag-classes-become-contextservice)
- [3. Either becomes Result](#3-either-becomes-result)
- [4. Cause is flat](#4-cause-is-flat)
- [5. The catch family is renamed](#5-the-catch-family-is-renamed)
- [6. Forking is renamed, and a Fiber is not an Effect](#6-forking-is-renamed-and-a-fiber-is-not-an-effect)
- [7. Subtyping gives way to Yieldable](#7-subtyping-gives-way-to-yieldable)
- [8. Keeping the process alive](#8-keeping-the-process-alive)
- [9. Layers memoize across provide calls](#9-layers-memoize-across-provide-calls)
- [10. FiberRef becomes Context.Reference](#10-fiberref-becomes-contextreference)
- [11. Runtime is gone](#11-runtime-is-gone)
- [12. Smaller shifts that still change a habit](#12-smaller-shifts-that-still-change-a-habit)
- [See also](#see-also)

---

## Where the per-symbol answer lives

This chapter will not tell you what a v3 function is called in v4. Effect publishes that, and it is more complete and more current than anything here. All of it is in `Effect-TS/effect` at the release tag matching your install (`effect@4.0.0` for 4.0.0):

| Question | Where |
| --- | --- |
| What changed, and the index of guides | `MIGRATION.md` |
| Why and how, one guide per shift | `migration/<topic>.md`: `services`, `cause`, `error-handling`, `forking`, `yieldable`, `fiberref`, `runtime`, `layer-memoization`, `fiber-keep-alive`, `scope`, `equality`, `generators`, `schema` |
| What a specific v3 import or symbol became | `migration/v3-to-v4.md`, a generated 1.4 MB reference: an import map first, then one line per v3 export. Search it for the symbol; never read it whole. Its per-API notes come from `migration/annotations/*.yaml` |
| Doing a port, mechanically | the `effect-v3-to-v4` skill in `Effect-TS/skills` |
| What a symbol is in the version you have installed | the installed package: `AGENTS.md`, `ai-docs/`, `dist/**/*.d.ts` |

Treat the installed package as the tiebreaker. The upstream skills and guides were written against a moving target; a few of their examples do not hold in 4.0.0, and this chapter says which.

---

## 1. One package, one version

**Was.** `effect` and its siblings (`@effect/platform`, `@effect/rpc`, `@effect/cluster`, `@effect/sql`, and so on) were separate packages with independent version numbers, and working out which `@effect/platform` went with which `effect` was a task in itself.

**Now.** The platform, rpc, cluster, http-api, cli, sql core and similar code moved into `effect` itself, and every ecosystem package that remains separate shares `effect`'s version: with `effect@4.0.0`, the matching driver is `@effect/sql-pg@4.0.0`. The packages that stay separate are platform-specific (`@effect/platform-*`), provider-specific (`@effect/sql-*` drivers, `@effect/ai-*`, `@effect/opentelemetry`), technology-specific (`@effect/atom-*`, `@effect/vitest`).

The consolidated code is imported by path under `effect/`: `effect/http/HttpRouter`, `effect/ai/LanguageModel`. During the pre-release the same modules lived under `effect/unstable/<group>/...`; **that segment no longer exists** and there are no compatibility exports for it. A guide, a blog post or a skill that still shows an `effect/unstable/` specifier predates 4.0.0.

**Drop the habit** of reading a package's version as independent of `effect`'s, and of reading a path as the signal for how stable an export is. Neither holds. Stability is looked up per export, and versions move together: both are the subject of [Stability](02-stability.md).

**Upstream:** `MIGRATION.md`, sections "Versioning", "Package Consolidation" and "Unstable Module System".

---

## 2. Services: Tag classes become Context.Service

**Was.** Services were declared with a tag constructor: a generic tag, a tag class, or a `Service` class that also generated a `.Default` layer and took a `dependencies` list. A tag class could also expose its methods as static accessors, so `Notifications.notify("hi")` worked without yielding the service first.

**Now.** One constructor, `Context.Service`, replaces all of them. The class form takes the type parameters first and the identifier second, so the order is the reverse of v3's tag class. A `make` option stores the constructor effect on the class, **but nothing generates a layer from it and there is no `dependencies` option**: you write the layer (`Layer.effect(this, this.make)`) and wire dependencies with `Layer.provide`. Static accessors are gone: use `yield*` on the service, or `use` for a one-off.

**Drop the habits:**

- Expecting `X.Default` to exist. Define `static readonly layer` yourself; v4's convention is `layer` for the primary layer and a suffix for variants (`layerTest`).
- Calling a service method statically. The accessor proxy erased generics and overloads, which is why it was removed.
- Reaching for `use` as the default. It hides the dependency at the call site; `yield*` in a generator keeps it visible.

How to define one is covered, with runnable examples, by the package's own `AGENTS.md` ("Writing Effect services") and not repeated here.

**Upstream:** `migration/services.md`.

---

## 3. Either becomes Result

**Was.** `Either<R, L>`, with `Right` and `Left`, and `either` to turn an effect into one that succeeds with an `Either`.

**Now.** The module is `Result` and the type is `Result<A, E = never>`, success first. The variants are `Success` and `Failure`. `Effect.result` turns an effect into one that succeeds with a `Result`. Several APIs that used to return `Option` or `Either` now return `Result`, for example `Cause.findError`.

**Drop the habit** of `Right`/`Left` and of treating `Either` as an import that exists. There is no `Either` module in 4.0.0.

**Upstream:** `migration/v3-to-v4.md`, "Import Map" (`effect/Either -> effect/Result`) and the per-API notes that begin `"effect/Either#..."` in `migration/annotations/effect__Either.yaml`. `MIGRATION.md` has no dedicated guide for this one; it is covered only by the generated reference.

---

## 4. Cause is flat

**Was.** A recursive tree of `Empty`, `Fail`, `Die`, `Interrupt`, `Sequential` and `Parallel`, walked recursively.

**Now.** `Cause<E>` wraps one array, `cause.reasons`, whose elements are `Fail`, `Die` or `Interrupt`. An empty cause is an empty array. Two failures, from a failed finalizer or from concurrent siblings, sit side by side in that array: `Cause.combine` concatenates, and **the sequential-versus-parallel distinction is no longer recorded**. Predicates moved from the cause level to the reason level (`Cause.isFailReason`) and the cause-level ones were renamed (`Cause.hasFails`, `Cause.hasDies`).

```ts
import { Cause } from "effect"

const describe = (cause: Cause.Cause<string>) => {
  const failures = cause.reasons.filter(Cause.isFailReason).map((reason) => reason.error)
  const defects = cause.reasons.filter(Cause.isDieReason).length
  return { failures, defects, interrupted: Cause.hasInterrupts(cause) }
}
```

**Drop the habit** of recursing over `left` and `right`, and of branching on `Sequential` or `Parallel`. Iterate `reasons`. A `*Exception` error class is now `*Error` (`Cause.TimeoutError`), and a few were removed outright; look the specific one up.

**Upstream:** `migration/cause.md`.

---

## 5. The catch family is renamed

**Was.** `catchAll`, `catchAllCause`, `catchAllDefect`, `catchSome`, `catchSomeCause`, `catchSomeDefect`, alongside `catchTag`, `catchTags` and `catchIf`.

**Now.** `Effect.catch`, `Effect.catchCause`, `Effect.catchDefect`. `catchTag`, `catchTags` and `catchIf` are unchanged. The `catchSome` family is replaced by `Effect.catchFilter` and `Effect.catchCauseFilter`, which take a `Filter` instead of a function returning an `Option`; `catchSomeDefect` has no replacement. New in v4: `Effect.catchReason` and `Effect.catchReasons`, for handling one nested `reason` of a tagged error without removing the parent from `E`.

```ts
import { Effect, Filter } from "effect"

// What a v3 catchSome handler becomes: a predicate lifted to a Filter.
const recovered = Effect.fail(42).pipe(
  Effect.catchFilter(
    Filter.fromPredicate((error: number) => error === 42),
    () => Effect.succeed("caught")
  )
)
```

**Drop the habit** of typing `catchAll`. In v4 the plain name `Effect.catch` is the catch-everything combinator, so a muscle-memory rename of "catchAll" to "catch" is the whole fix for most call sites.

**Upstream:** `migration/error-handling.md`.

---

## 6. Forking is renamed, and a Fiber is not an Effect

**Was.** `fork`, `forkDaemon`, `forkScoped`, `forkIn`, `forkAll`, `forkWithErrorHandler`; and a `Fiber` was itself an `Effect`, so `yield* fiber` joined it.

**Now.** `Effect.forkChild` (was `fork`) and `Effect.forkDetach` (was `forkDaemon`). `forkScoped` and `forkIn` keep their names. `forkAll` and `forkWithErrorHandler` are removed. All four that remain take an options object with `startImmediately` and `uninterruptible`. A fiber is a plain value: you join it with `Fiber.join` or wait with `Fiber.await`.

```ts
import { Effect, Fiber } from "effect"

const program = Effect.gen(function*() {
  const fiber = yield* Effect.forkChild(Effect.succeed(1), { startImmediately: true })
  return yield* Fiber.join(fiber)
})
```

**Drop the habits:** `yield* fiber`, and the bare `fork`. For the removed combinators, fork the effects individually or use a higher-level concurrency combinator, and observe a forked fiber's failure through `Fiber.join` or `Fiber.await`. Note that "child" is now in the name: `forkChild` is the structured-concurrency fork, `forkDetach` is the one that outlives its parent.

**Upstream:** `migration/forking.md` (the rename and the options), `migration/yieldable.md` ("Types No Longer Subtypes of Effect", for the fiber).

---

## 7. Subtyping gives way to Yieldable

**Was.** Many values were structural subtypes of `Effect` and could be passed anywhere an effect was expected: `Ref`, `Deferred`, `Fiber`, `FiberRef`, `Config`, `Option`, `Either`, and tags. The convenience caused real bugs: a `Ref` handed to `Effect.map` silently read the ref instead of failing to type-check, and `Effect.all` over an array of refs read all of them.

**Now.** The set of values that are effects is much smaller. Upstream names the narrower contract `Yieldable`: something `yield*` accepts inside a generator without being assignable to `Effect`. Checked against `effect@4.0.0`:

| Value | In 4.0.0 |
| --- | --- |
| `Ref`, `Deferred`, `Fiber` | Plain values. Use `Ref.get`, `Deferred.await`, `Fiber.join` |
| `Option`, `Result` | Not effects, and **not yieldable in `Effect.gen`** (see below). Convert with `Effect.fromOption` and `Effect.fromResult` |
| A `Context.Service` class, a `Config` value, an `Exit`, a tagged error | Still effects: yield them directly |

**Where the package disagrees with the guide.** Upstream's `yieldable.md` shows `yield* Option.some(42)` working in `Effect.gen` and an `.asEffect()` method on `Option`. On the published 4.0.0, neither holds: the call is a type error, a program that gets past the compiler fails at run time with `Not a valid effect`, there is no `asEffect` on `Option` or `Result`, and no export of the package is named `Yieldable`. `Option.gen` and `Result.gen` are their own generators, and the bridge into an effect is the pair of functions below. Do not paste the guide's `Option` and `Result` examples.

```ts
import { Effect, Option, Result } from "effect"

const lookup = (id: string): Option.Option<string> => (id === "1" ? Option.some("ada") : Option.none())
const parse = (s: string): Result.Result<number, string> => {
  const n = Number(s)
  return Number.isNaN(n) ? Result.fail(`not a number: ${s}`) : Result.succeed(n)
}

const program = Effect.gen(function*() {
  const name = yield* Effect.fromOption(lookup("1"), () => "no such user")
  const n = yield* Effect.fromResult(parse("42"))
  return `${name}:${n}`
})
```

**Drop the habits:** `yield* ref`, `yield* deferred`, `yield* fiber`, and passing an `Option` or an `Either`-shaped value straight to an `Effect` combinator. When the compiler rejects one of these, the fix is the module function, not a cast.

**Upstream:** `migration/yieldable.md` (the rationale and the `Ref`, `Deferred` and `Fiber` cases hold; the `Option` and `Result` cases do not hold on 4.0.0).

---

## 8. Keeping the process alive

**Was.** A program whose only remaining work was a suspended fiber let the Node process exit. `runMain` from a platform package held it open with a long timer.

**Now, per upstream:** `migration/fiber-keep-alive.md` says the keep-alive moved into the core fiber runtime, so a bare `Effect.runPromise` of a suspended program stays alive.

**On 4.0.0 as published, that is not what happens.** Running `Effect.runPromise` or `Effect.runFork` over `Effect.never`, or over a `Deferred` nobody completes, exits with status 0 immediately. The only keep-alive timer in the package is installed by `Runtime.makeRunMain`, the runner factory that `NodeRuntime.runMain` is built on; a program run through `NodeRuntime.runMain` over `Effect.never` stays alive until signalled. Upstream's own test for this (`EffectKeepAlive.test.ts` at the tag) exercises `makeRunMain`, not `runPromise`. So the v3 rule survives: **the long-running entry point goes through `runMain`**, which also gives you signal handling, exit codes and error reporting.

**Drop the habit** of believing either version of the story without running it. If your program's lifetime depends on a suspended fiber, run it through `runMain`; do not rely on `runPromise` to hold the process open.

**Upstream:** `migration/fiber-keep-alive.md` (its "runMain Is Still Recommended" section is the part that matches the package).

---

## 9. Layers memoize across provide calls

**Was.** Each `Effect.provide` built its own memoization scope, so the same layer provided twice was built twice.

**Now.** The memo map is shared, so a layer provided more than once is built once. Opt out per layer with `Layer.fresh`, or per provide with the new `{ local: true }` option.

The sharing has limits (it reaches nested provides, not sibling programs, and upstream's own `{ local: true }` example comment does not match the package), and the measured table is in [Pitfalls](04-pitfalls.md), "Layer sharing". Count builds in a test when isolation matters; do not trust the option name.

```ts
import { Context, Effect, Layer } from "effect"

class Db extends Context.Service<Db, { readonly url: string }>()("app/Db") {
  static readonly layer = Layer.succeed(Db, { url: "memory" })
}

const program = Effect.gen(function*() {
  return (yield* Db).url
})

// Compose, then provide once. Memoization is a safety net, not the design.
const main = program.pipe(Effect.provide(Db.layer))

// A test that must not share state with its surroundings opts out.
const isolated = program.pipe(Effect.provide(Db.layer, { local: true }))
```

**Drop the habit** of provide-per-call wiring that "works because each call is separate", and the opposite habit of defensively wrapping layers in `Layer.fresh` to avoid double acquisition. Upstream's own advice, which holds: compose layers first and provide once. How the graph is assembled around this is in [Architecture](03-architecture.md).

**Upstream:** `migration/layer-memoization.md`.

---

## 10. FiberRef becomes Context.Reference

**Was.** Fiber-local state was a `FiberRef`, read with `FiberRef.get`, written with `set`, and scoped with `locally`. The built-ins (`currentLogLevel` and friends) were `FiberRef` values.

**Now.** `FiberRef`, `FiberRefs`, `FiberRefsPatch` and `Differ` are gone. Fiber-local state is a `Context.Reference`, the same mechanism as a service with a default. The built-ins live in the `References` module (`References.CurrentLogLevel`, `References.MinimumLogLevel`, `References.MaxOpsBeforeYield`, among others). You read one by yielding it; you scope a value over an effect with `Effect.provideService`.

```ts
import { Effect, References } from "effect"

const program = Effect.gen(function*() {
  return yield* References.CurrentLogLevel
})

// Scoped to this effect only. There is no mutating set.
const quiet = Effect.provideService(program, References.MinimumLogLevel, "Error")
```

**Drop the habits:** `get` and `set` on a ref, and `locally`. A value that must change for the rest of a fiber's life is now a value you provide around the code that should see it. A log level is passed as a string literal such as `"Debug"`.

**Upstream:** `migration/fiberref.md`, with the full v3-to-v4 table of built-ins.

---

## 11. Runtime is gone

**Was.** `Runtime<R>` bundled a context, runtime flags and fiber refs, and was how you ran an effect from outside the program: take `runtime<R>()`, then call a `Runtime` run function.

**Now.** The `Runtime<R>` type and its run functions are removed. Take the services with `Effect.context<R>()`, which gives a `Context<R>`, and run with `Effect.runForkWith(services)`. If the effect needs no services, call `Effect.runFork`. **The `Runtime` module itself still exists in 4.0.0**, which is what makes this easy to misread: upstream's guide lists its remaining contents as `Teardown`, `defaultTeardown` and `makeRunMain`; the package also exports `errorExitCode`, `errorReported`, `getErrorExitCode` and `getErrorReported`. What went away is the `Runtime<R>` value and everything that took or returned one; what remains is process-lifecycle code.

```ts
import { Context, Effect } from "effect"

class Logger extends Context.Service<Logger, { readonly log: (message: string) => void }>()("app/Logger") {}

const job = Effect.gen(function*() {
  const logger = yield* Logger
  logger.log("hello")
})

// Running effects from inside an effect, with the current services.
const main = Effect.gen(function*() {
  const services = yield* Effect.context<Logger>()
  return Effect.runForkWith(services)(job)
})
```

**Drop the habit** of threading a `Runtime` through callbacks and framework adapters. Thread a `Context` (or capture `Effect.context`) instead.

**Upstream:** `migration/runtime.md`.

---

## 12. Smaller shifts that still change a habit

These are short. Each has an upstream guide; read it before relying on the one-line version here.

- **Structural equality by default.** `Equal.equals` on plain objects, arrays, `Map`s, `Set`s and `Date`s now compares by value, and `NaN` equals `NaN`. A reference check you used to get from `Equal.equals` now needs `Equal.byReference`. The wrapper to `Equivalence` was renamed `Equal.asEquivalence`. Drop the habit of wrapping data in a `Data` constructor only to make equality structural. *Upstream:* `migration/equality.md`.
- **`extend` on `Scope` is `Scope.provide`.** Same behaviour: it supplies a scope to an effect that requires one without closing the scope afterwards. *Upstream:* `migration/scope.md`.
- **`Effect.gen` and `this`.** A `self` is no longer the first argument: pass `Effect.gen({ self: this }, function*() { ... })`. *Upstream:* `migration/generators.md`.
- **Schema changed a lot.** Renamed decoders and encoders (the Effect-returning ones carry an `Effect` suffix), array arguments where v3 took variadic ones, and filters and field-picking restructured. This is the largest single guide and the one most worth reading in full before touching schema code. *Upstream:* `migration/schema.md`, which classifies each change as auto, semi-auto, manual or removed.
- **Import paths.** Dropping the `unstable` path segment is covered in shift 1. The 4.0.0 specifier for the HTTP router is `effect/http/HttpRouter`.

---

## See also

- [Stability](02-stability.md): how to tell what can break in a minor release, now that the path does not say.
- [Architecture](03-architecture.md): layering and where the layer graph is built.
- [Pitfalls](04-pitfalls.md): the mistakes that recur, including ones these shifts cause.
- The installed package's `AGENTS.md` and `ai-docs/`: API facts for the version you have.
- Upstream: `MIGRATION.md` and `migration/` in `Effect-TS/effect` at your tag; the `effect-v3-to-v4` skill in `Effect-TS/skills` for doing a port.
