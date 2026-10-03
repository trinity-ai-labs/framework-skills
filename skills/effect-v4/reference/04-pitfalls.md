<!-- verified: effect@4.0.0 -->
# Pitfalls in Effect 4

> **When you reach for this:** something "doesn't run", runs once when you expected many, exits the process with no error, leaks a resource, or an `R` or `E` type will not resolve. These are the mistakes that cost time in `effect@4.0.0`, each with the fix beside it, and a closing section on reading a type that will not collapse.

Every entry was checked against the installed `effect@4.0.0`: by compiling it, by running a program and reading what it printed, or by reading the source. Where upstream's migration guides and the published package disagree, the package wins and the entry says so. Entries are tagged **unchanged from v3** (possibly with renamed API), **changed since v3** or **new in v4**. A reader coming from v3 should read the changed and new ones first. Upstream's `migration/` guides, cited below, are in the `Effect-TS/effect` repository at the tag `effect@4.0.0`, not in the installed package. Examples assume the modules they use are imported from `effect`; a `❌` block is the wrong side and is never the thing to copy.

The bundled guide (`AGENTS.md` in the package root, and `ai-docs/`) already covers how to write services, errors and layers. This chapter does not repeat it; it records what goes wrong.

## Contents

- [1. Building an effect is not running it](#1-building-an-effect-is-not-running-it)
- [2. all and forEach are sequential by default](#2-all-and-foreach-are-sequential-by-default)
- [3. Running effects inside effects](#3-running-effects-inside-effects)
- [4. Throwing and try-catch inside gen](#4-throwing-and-try-catch-inside-gen)
- [5. Swallowing errors with a catch-all](#5-swallowing-errors-with-a-catch-all)
- [6. catchTag and catch do not see defects](#6-catchtag-and-catch-do-not-see-defects)
- [7. Real timers, Date.now and Math.random](#7-real-timers-datenow-and-mathrandom)
- [8. Resources without a scope](#8-resources-without-a-scope)
- [9. Layer sharing: fresh, local and nested provides](#9-layer-sharing-fresh-local-and-nested-provides)
- [10. provide versus provideMerge](#10-provide-versus-providemerge)
- [11. Service key collisions](#11-service-key-collisions)
- [12. Long synchronous loops block interruption](#12-long-synchronous-loops-block-interruption)
- [13. Not decoding untrusted input](#13-not-decoding-untrusted-input)
- [14. Casting to dodge the R or E channel](#14-casting-to-dodge-the-r-or-e-channel)
- [15. Reinventing primitives](#15-reinventing-primitives)
- [16. Ceremony around gen](#16-ceremony-around-gen)
- [17. A program that only waits exits silently](#17-a-program-that-only-waits-exits-silently)
- [18. Yielding an Option, a Result or a Ref](#18-yielding-an-option-a-result-or-a-ref)
- [19. Reading a Cause as a tree](#19-reading-a-cause-as-a-tree)
- [20. Passing this to gen](#20-passing-this-to-gen)
- [21. Equality is structural now](#21-equality-is-structural-now)
- [22. A forked child ends with its parent](#22-a-forked-child-ends-with-its-parent)
- [23. Leaning on an unstable export without pinning](#23-leaning-on-an-unstable-export-without-pinning)
- [24. Importing through a pre-release path](#24-importing-through-a-pre-release-path)
- [What changed in the v3 list](#what-changed-in-the-v3-list)
- [Diagnosing a messy E or R](#diagnosing-a-messy-e-or-r)
- [See also](#see-also)

## 1. Building an effect is not running it

**Unchanged from v3.** An `Effect` is a description. Constructing one has no side effect, and a `gen` block that builds an effect and never yields it drops it.

```ts
// ❌ Builds the effect and discards it. Nothing is saved, and nothing is reported.
const bad = Effect.gen(function*() {
  saveUser(user)
})
```

```ts
// ✅ Yield it, or hand it to a runner at the edge.
const good = Effect.gen(function*() {
  yield* saveUser(user)
})
```

Confirmed on 4.0.0: a side-effecting `Effect.sync` built inside `gen` without `yield*` never ran, with or without the surrounding effect being run. TypeScript will not flag the dropped value. Upstream's own tsconfig runs the `@effect/language-service` plugin, which has a `floatingEffect` diagnostic for exactly this (`ai-docs/tsconfig.json` in the package turns it off for its examples, which is how you can tell it exists).

## 2. all and forEach are sequential by default

**Unchanged from v3.** The `concurrency` option defaults to sequential for both. Measured on 4.0.0, four 50 ms sleeps took 207 ms under `Effect.all` and 209 ms under `Effect.forEach` with no option, and 54 ms with `concurrency: 4` or `"unbounded"`.

```ts
// ❌ One at a time.
const slow = Effect.all(ids.map(fetchUser))
```

```ts
// ✅ Say how many at once. Bound it for anything that hits a real resource.
const bounded = Effect.all(ids.map(fetchUser), { concurrency: 10 })
const fanOut = Effect.forEach(ids, fetchUser, { concurrency: "unbounded" })
```

Use `"unbounded"` only when the work is cheap or already rate-limited elsewhere.

## 3. Running effects inside effects

**Unchanged from v3.** A nested `Effect.runSync` or `Effect.runPromise` starts a fresh run with none of the caller's services, interruption or tracing. On 4.0.0 a nested `Effect.runSync` of an effect that needs a service, called from inside code that had provided it, failed with `Service not found: <key>`.

```ts
// ❌ Never run inside business logic.
const handler = Effect.sync(() => Effect.runSync(fetchUser(id)))
```

```ts
// ✅ Stay inside Effect and run once at the entry point.
const handler = Effect.gen(function*() {
  return yield* fetchUser(id)
})
```

If you must call back into Effect from foreign code that was started inside a run, capture the services with `Effect.context` and run with `Effect.runForkWith(services)`; upstream's `migration/runtime.md` has the pattern.

## 4. Throwing and try-catch inside gen

**Unchanged from v3, renamed wrappers.** The generator is not an `async` function. On 4.0.0:

- `try`/`catch` around `yield*` does not catch a typed failure. The failure ends the generator and the `catch` block never runs.
- A `throw` inside `gen` does not become a typed error. It becomes a defect (`Die`).

```ts
// ❌ Neither the catch block nor the type system sees this error.
const bad = Effect.gen(function*() {
  try {
    return yield* fetchUser(id)
  } catch (e) {
    return defaultUser
  }
})
```

```ts
// ✅ Errors are values in E. Recover with combinators.
const good = fetchUser(id).pipe(
  Effect.catchTag("UserNotFound", () => Effect.succeed(defaultUser))
)
```

To bring a throwing or promise-returning API in, wrap it: `Effect.try`, `Effect.tryPromise`, or `Effect.callback` for callback APIs. v3's `async` constructor is gone, and without a `catch` option the wrapper fails with `Cause.UnknownError` (v3's `UnknownException`, renamed).

## 5. Swallowing errors with a catch-all

**Unchanged from v3, renamed.** `Effect.catch` is the empty `catch {}` of Effect: it recovers from every typed failure and discards the evidence. (It is v3's `catchAll`; the name `catchAll` does not exist in 4.0.0.)

```ts
// ❌ Every failure becomes null. No log, no metric, no signal.
const bad = fetchUser(id).pipe(Effect.catch(() => Effect.succeed(null)))
```

```ts
// ✅ Handle the case you know about; let the rest propagate.
const known = fetchUser(id).pipe(
  Effect.catchTag("UserNotFound", () => Effect.succeed(null))
)

// ✅ Or recover at a real boundary, but record it.
const boundary = fetchUser(id).pipe(
  Effect.tapError((e) => Effect.logError(e)),
  Effect.catch(() => Effect.succeed(null))
)
```

Reserve `Effect.catch` for a boundary that genuinely handles every case. The bundled guide shows `catchTag` with several tags at once (`ai-docs/src/01_effect/04_errors/10_catch-tags.ts`).

## 6. catchTag and catch do not see defects

**Unchanged from v3, renamed.** The `catch` family reads the `E` channel only. A defect (`Effect.die`, a throw inside `Effect.sync`, a bug) travels as a `Die` and passes straight through. Measured on 4.0.0: `Effect.die("boom")` piped to `Effect.catch` was not caught; the same piped to `Effect.catchDefect` was. A throw inside `Effect.sync` behaved the same. `Effect.orDie` turns a typed failure into a defect, after which `catch` no longer sees it either.

```ts
// ❌ Only typed failures. A defect still kills the fiber.
const missed = risky.pipe(Effect.catch(() => Effect.succeed("recovered")))
```

```ts
// ✅ Cause-level handlers see defects.
const defects = risky.pipe(Effect.catchDefect(() => Effect.succeed("recovered")))
const everything = risky.pipe(Effect.catchCause(() => Effect.succeed("recovered")))
```

Defects should usually crash, so reach for these at a true boundary (a request handler, a worker loop) and log what you catch. v3's `catchAllCause` and `catchAllDefect` are these two renamed; `catchSomeDefect` is not exported by 4.0.0.

## 7. Real timers, Date.now and Math.random

**Unchanged from v3.** Reaching for the platform makes code untestable, and its timers are not under the runtime's control. The Effect services are interruptible and controllable under the test clock.

```ts
// ❌
const sleepy = Effect.promise(() => new Promise((r) => setTimeout(r, 1000)))
const now = Date.now()
const roll = Math.random()
```

```ts
// ✅ Interruptible, and driven by TestClock in tests.
const sleep = Effect.sleep("1 second")
const timed = Effect.gen(function*() {
  const now = yield* Clock.currentTimeMillis
  const roll = yield* Random.next
  return [now, roll] as const
})
```

The test clock lives in `effect/testing`. Without a test runner, provide its layer and adjust time yourself. On 4.0.0 this advanced an hour of virtual time in about a millisecond of real time:

```ts
import { TestClock } from "effect/testing"

const hour = Effect.gen(function*() {
  const start = yield* Clock.currentTimeMillis
  yield* Effect.sleep("1 hour")
  return (yield* Clock.currentTimeMillis) - start
})

const test = Effect.gen(function*() {
  const fiber = yield* Effect.forkChild(hour)
  yield* TestClock.adjust("1 hour")
  return yield* Fiber.join(fiber) // 3600000
}).pipe(Effect.provide(TestClock.layer()))
```

`@effect/vitest`'s `it.effect` already provides it (`ai-docs/src/09_testing/10_effect-tests.ts`). For date arithmetic prefer the `DateTime` module over `Date`; the bundled guide says so.

## 8. Resources without a scope

**Changed since v3.** `Effect.acquireRelease` registers its finalizer in the current scope, and it adds `Scope` to `R`. With no scope the type does not collapse, and if you cast past it the program fails at run time. On 4.0.0 an unscoped run failed with `Service not found: effect/Scope`, and the resource was never even opened.

```ts
// ❌ R is Scope here, so this does not type-check.
const bad = Effect.acquireRelease(open, close).pipe(Effect.flatMap(use))
```

```ts
// ✅ Close the scope where the work ends.
const scoped = Effect.acquireRelease(open, close).pipe(
  Effect.flatMap(use),
  Effect.scoped
)

// ✅ For an application-lifetime resource, build the service layer from it.
class Pool extends Context.Service<Pool, { readonly size: number }>()("app/Pool") {
  static readonly layer = Layer.effect(
    Pool,
    Effect.acquireRelease(Effect.succeed({ size: 4 }), () => Effect.log("pool closed"))
  )
}
```

What changed: v3's scoped layer constructor is gone (`scoped` is not exported by `Layer` in 4.0.0). `Layer.effect` takes a scoped effect and removes `Scope` from the requirement itself; compiling the layer above gives `Layer<Pool, never, never>`. v3's `extend` on `Scope` became `Scope.provide`. Do not hand-roll `try`/`finally`: measured on 4.0.0, a release function ran when its fiber was interrupted and a `finally` block inside `gen` did not. See `ai-docs/src/01_effect/05_resources/10_acquire-release.ts`.

## 9. Layer sharing: fresh, local and nested provides

**Changed since v3.** In v3 every `Effect.provide` call had its own memo scope, so the same layer provided twice was built twice. In 4.0.0 the memo map is shared between `provide` calls, so it is built once. Two traps follow: reaching for `Layer.fresh` "to be safe" and double-acquiring a pool, and expecting `{ local: true }` to isolate more than it does.

Measured on 4.0.0, counting how many times a layer's constructor ran:

| Pipeline | Builds |
| --- | --- |
| `provide(L)` then `provide(L)` | 1 |
| `provide(L)` then `provide(Layer.fresh(L))`, either order | 2 |
| `provide(L)` inner, `provide(L, { local: true })` outer | 1 |
| `provide(L, { local: true })` inner, `provide(L)` outer | 2 |
| `Layer.merge(L, Layer.fresh(L))` | 2 |

The fourth row is the one to know. `local: true` builds with a private memo map and hands that map to everything inside the call, including `provide` calls nested in it, which then reuse it. Upstream's `migration/layer-memoization.md` comments its own `local` example as building twice; the outer-`local` order it shows measured once here. Put `local: true` on the call whose subtree must get its own instances.

```ts
// ❌ "To be safe": the pool is acquired twice.
const doubled = Layer.merge(DbLive, Layer.fresh(DbLive))
```

```ts
// ✅ Define once, reference everywhere, compose. Sharing is the default.
const main = program.pipe(Effect.provide(AppLive))

// ✅ When a test needs its own instances, isolate that one provide.
const isolated = program.pipe(Effect.provide(AppLive, { local: true }))
```

Compose layers before providing; upstream's `migration/layer-memoization.md` calls the shared memo map "a safety net, not a substitute" for composition. How the graph is assembled is in [Architecture](03-architecture.md).

## 10. provide versus provideMerge

**Unchanged from v3.** `Layer.provide` satisfies a layer's inputs and hides the provider from the output. `Layer.provideMerge` satisfies them and keeps the provider in the output. Compiled on 4.0.0, with `RepoLive` requiring `Database`:

```ts
// Layer<Repo, never, never>: Database is internal plumbing.
const hidden = RepoLive.pipe(Layer.provide(DbLive))
// Layer<Database | Repo, never, never>: Database is now part of the surface.
const exposed = RepoLive.pipe(Layer.provideMerge(DbLive))
```

Using `provideMerge` everywhere leaks internal services into your public layer, and callers start depending on them. Use `provide` for plumbing and `provideMerge` only when the dependency is part of what you expose. The example in the package is `ai-docs/src/01_effect/03_services/20_layer-composition.ts`.

## 11. Service key collisions

**Changed since v3 in its API, same trap.** A service is a slot in a map keyed by its string identifier. Two services with the same key are one slot, and nothing checks the types. On 4.0.0, a service `B` declared with the same key as `A` resolved to the value provided for `A`, typed as `B`.

```ts
// ❌ Bare keys collide across modules.
class Config extends Context.Service<Config, { readonly port: number }>()("Config") {}
class AuthConfig extends Context.Service<AuthConfig, { readonly secret: string }>()("Config") {}
```

```ts
// ✅ Namespace every key with the package and path, as the bundled guide does.
class Settings extends Context.Service<Settings, { readonly port: number }>()("app/config/Settings") {}
```

v3's `GenericTag`, `Tag` and `Service` on `Effect` are gone; `Context.Service` is the one constructor. The function form (`Context.Service<Shape>("key")`) has the same collision rule.

## 12. Long synchronous loops block interruption

**Unchanged from v3.** Fibers are cooperative. One synchronous callback is never interrupted and starves other fibers. Measured on 4.0.0 with an interrupt requested at 50 ms: a single `Effect.sync` containing the whole loop ended after 3305 ms. The same work as an effectful loop, one step per `yield*`, ended after 54 ms. The runtime already yields between steps; you only need to split the work.

```ts
// ❌ One uninterruptible block.
const blocked = Effect.sync(() => {
  for (let i = 0; i < 1e9; i++) heavy(i)
})
```

```ts
// ✅ Make each step an effect so the runtime can interrupt between them.
const stepped = Effect.forEach(Array.range(0, 1000), (i) => Effect.sync(() => heavy(i)), {
  discard: true
})

// ✅ Or keep one loop and yield every so often.
const looped = Effect.gen(function*() {
  for (let i = 0; i < 1e9; i++) {
    heavy(i)
    if (i % 1000 === 0) yield* Effect.yieldNow
  }
})
```

## 13. Not decoding untrusted input

**Changed since v3 in its names.** `JSON.parse` returns `any`, and a cast over it defeats the type system at the boundary that matters most. Decode with a `Schema`; the failure is a `SchemaError` in `E` (v3's `ParseError`), and `decodeUnknown` was renamed `decodeUnknownEffect`.

```ts
// ❌ A cast is not validation.
const body = JSON.parse(raw) as CreateUser
```

```ts
// ✅ A typed value, or a SchemaError you can handle.
const CreateUser = Schema.Struct({ name: Schema.String, age: Schema.Number })
const decodeBody = Schema.decodeUnknownEffect(Schema.fromJsonString(CreateUser))

const handle = (raw: string) =>
  Effect.gen(function*() {
    const body = yield* decodeBody(raw)
    return body.name
  })
```

On 4.0.0 `{"name":"a","age":"x"}` failed with a `SchemaError` reading `Expected number` at `["age"]`. Decode at the edge and trust the type inside. The guide covers the rest (`ai-docs/src/01_effect/02_schema/10_schema-basics.ts`).

## 14. Casting to dodge the R or E channel

**Unchanged from v3.** A non-`never` `R` at the entry point, or an `E` you did not want, is the compiler doing its job. A cast moves a compile-time error to a run-time defect. Measured on 4.0.0: running a service-requiring effect cast to `Effect<number>` produced a `Die` reading `Service not found: <key>`.

```ts
// ❌ "It compiles now."
Effect.runPromise(program as unknown as Effect.Effect<number>)
```

```ts
// ✅ Provide the dependency, then there is nothing to cast.
Effect.runPromise(program.pipe(Effect.provide(MainLive)))
```

If `R` will not reach `never`, wire the missing layer. See the diagnosis section below.

## 15. Reinventing primitives

**Changed since v3 in its names.** Before hand-rolling, look for the library's own. Every name here was looked up in the 4.0.0 snapshot.

| You wrote | Use instead |
| --- | --- |
| a retry loop around `setTimeout` | `Effect.retry` with a `Schedule` |
| a hand-written debounce or throttle | `Stream.debounce`, `Stream.throttle` |
| a mutex built from a boolean | `Semaphore.make` (v3's `makeSemaphore` is gone) |
| shared mutable state in a closure | `Ref`, `SynchronizedRef` |
| a one-shot "wait for X" flag | `Deferred` |
| `Promise.all` plus error juggling | `Effect.all` with `concurrency` |
| `try`/`finally` cleanup | `Effect.acquireRelease`, `Effect.ensuring` |
| your own `isRecord` or `isString` | the `Predicate` module, e.g. `Predicate.isObject` (the bundled guide forbids writing these) |
| `Date.now()` and date maths | `Clock`, `DateTime` |
| a hand-written config parser | `Config` plus `Schema` |

## 16. Ceremony around gen

**Unchanged from v3, with one v4 addition.** `Effect.gen` is for sequential or branching logic. A single transform does not need it, and a deep `flatMap` pyramid is what `gen` is for.

```ts
// ❌ A generator for one map.
const verbose = Effect.gen(function*() {
  const u = yield* fetchUser(id)
  return u.name
})
```

```ts
// ✅
const terse = fetchUser(id).pipe(Effect.map((u) => u.name))
```

The v4 addition, from the bundled guide: a function that only wraps and returns an `Effect.gen` should be `Effect.fn("name")(function*(...) {...})`, which also attaches a span and a better stack trace. Use `Effect.fnUntraced` in library code and hot paths where you do not want a span. Add behaviour as further arguments to `Effect.fn`, not with `.pipe`.

```ts
// ✅
const loadName = Effect.fn("loadName")(function*(id: string) {
  const u = yield* fetchUser(id)
  return u.name
})
```

## 17. A program that only waits exits silently

**New in v4 (contradicts upstream's guide).** Upstream's `migration/fiber-keep-alive.md` says the core runtime now keeps the process alive while a fiber is suspended. On `effect@4.0.0` under Node 22 it does not. These all let the process exit with code 0 at once, without resolving:

- `Effect.runFork` and `Effect.runPromise` of a program that awaits a `Deferred` nobody completes
- `Effect.runPromise(Effect.never)` (the promise never settles and the process leaves anyway)

The keep-alive timer is created only by `Runtime.makeRunMain`, which is what the platform packages' `runMain` is built from. Running the same `Deferred` program through a `makeRunMain` runner stayed alive past the 4 s limit.

```ts
// ❌ Exits at once with code 0 while the program is still waiting.
Effect.runFork(waitsForever)
```

```ts
// ✅ runMain keeps the process alive, handles SIGINT and SIGTERM, and sets the exit code.
import { NodeRuntime } from "@effect/platform-node"

NodeRuntime.runMain(waitsForever)
```

`runMain` comes from `@effect/platform-node` (or the Bun, Deno or browser packages), not from `effect`. See `ai-docs/src/01_effect/06_running/`. This is also what "forgetting to run it" looks like in v4: not an error, but a clean exit.

## 18. Yielding an Option, a Result or a Ref

**Changed since v3.** In v3 `Option`, `Either`, `Ref`, `Deferred`, `Fiber` and `Config` were structurally `Effect`s, so you could `yield*` them and pass them to combinators. In 4.0.0 they are not.

- `yield* Option.some(1)` does not type-check, and at run time (past a cast) failed with a `Not a valid effect` error from the fiber run loop.
- `Effect.map(Option.some(1), f)` does not type-check.
- `yield* ref` fails with the unhelpful `Type 'Ref<number>' must have a '[Symbol.iterator]()' method that returns an iterator`.
- Neither `Option` nor `Result` has `asEffect` in 4.0.0, so upstream's `migration/yieldable.md` advice to call `.asEffect()` on them does not work. Use the bridges.

```ts
// ❌ v3 habits. None of these compile in v4.
// const a = yield* Option.some(1)
// const b = yield* ref
// const c = Effect.map(Option.some(1), (n) => n + 1)
```

```ts
// ✅ Convert explicitly, and read stateful values with their module.
const program = Effect.gen(function*() {
  const ref = yield* Ref.make(0)
  const a = yield* Effect.fromOption(Option.some(1)) // NoSuchElementError on None
  const b = yield* Effect.fromResult(Result.succeed(2))
  const c = yield* Ref.get(ref)
  return [a, b, c]
})
```

What still yields directly includes an `Effect`, a `Context.Service` class (to get the service) and a tagged error (to fail with it). For anything else, check with the compiler rather than from memory.

## 19. Reading a Cause as a tree

**Changed since v3.** `Cause<E>` is no longer a tree with `Empty`, `Sequential` and `Parallel` nodes. It is a flat object holding `reasons`, each `Fail`, `Die` or `Interrupt`. A v3 `switch (cause._tag)` does not compile, and at run time `_tag` is `undefined`. On 4.0.0 `Effect.all` over a failure and a defect, run concurrently, produced a flat `cause.reasons` (which reason it held depended on which branch finished first) and no tree.

```ts
// ❌ v3 shape: no _tag, no left or right.
// switch (cause._tag) { case "Sequential": ... case "Parallel": ... }
```

```ts
// ✅ Iterate the flat list; use the guards for the kind you want.
const kinds = (cause: Cause.Cause<string>) => cause.reasons.map((r) => r._tag)

const firstDefect = (cause: Cause.Cause<string>) => cause.reasons.find(Cause.isDieReason)
const hasDefect = (cause: Cause.Cause<string>) => Cause.hasDies(cause)
```

An empty cause is an empty `reasons` array. The v3 `*Exception` classes are `*Error` (`Cause.TimeoutError`, `Cause.UnknownError`). The per-symbol table is upstream's `migration/cause.md`.

## 20. Passing this to gen

**Changed since v3.** `Effect.gen(this, function*() {...})` was how a class method got `this`. In v4 the first argument is an options object, so the form is `Effect.gen({ self: this }, function*() {...})`. The old form fails the type check (`Argument of type 'this' is not assignable to parameter of type '{ readonly self: unknown; }'`). Past a cast it does not throw: on 4.0.0 the old form ran and a property read through `this` came back `undefined`, so the bug surfaces as a wrong value.

```ts
// ✅
class Counter {
  readonly step = 1
  next = Effect.gen({ self: this }, function*() {
    return yield* Effect.succeed(this.step + 1)
  })
}
```

## 21. Equality is structural now

**Changed since v3.** `Equal.equals` compares plain objects, arrays, `Map`, `Set` and `Date` by value, and `NaN` equals `NaN`. In v3 two distinct plain objects were never equal. Code that used effect collections or `Equal` expecting identity now merges values. On 4.0.0 `HashSet.make(a, b)` of two equal-valued plain objects had size 1; a built-in `Set` of the same two had size 2.

```ts
// ✅ Opt a value back into identity when you need it.
const a = { id: 1 }
const b = { id: 1 }
Equal.equals(a, b) // true in v4, false in v3
Equal.equals(Equal.byReference(a), b) // false
```

v3's `equivalence` is now `Equal.asEquivalence`. Upstream's guide is `migration/equality.md`.

## 22. A forked child ends with its parent

**Changed since v3 in its names.** v3's `fork` is gone. `Effect.forkChild` is the same structured child: it is interrupted when the parent ends. Measured on 4.0.0, a `forkChild` ticker stopped when its parent returned and a `forkDetach` ticker kept going. People moving a v3 `forkDaemon` to `forkChild` lose the background work.

```ts
// ❌ The ticker dies with main.
const bad = Effect.gen(function*() {
  yield* Effect.forkChild(ticker)
  yield* Effect.sleep("1 second")
})
```

```ts
// ✅ Tie it to a scope you control, or detach it deliberately.
const tied = Effect.gen(function*() {
  yield* Effect.forkScoped(ticker)
  yield* Effect.sleep("1 second")
}).pipe(Effect.scoped)

const detached = Effect.forkDetach(ticker)
```

Prefer `forkScoped` to `forkDetach`: a detached fiber has no owner, so nothing interrupts it. See `migration/forking.md` upstream.

## 23. Leaning on an unstable export without pinning

**New in v4.** The `effect` package now contains modules (`http`, `rpc`, `sql`, `cli`, `ai` and others) whose exports are tagged `@stability unstable`, and an unstable export may break in a minor release. The tier is a property of each export and the import path no longer shows it. Check before relying on one:

```sh
node <skill-dir>/scripts/stability.mjs effect/http/HttpRouter make
```

On 4.0.0 that prints `unstable`. A caret range on `effect` then lets `npm install` take a breaking change. Pin the exact version and keep use of unstable modules behind a thin module of your own. The discipline is owned by [Stability](02-stability.md); where that boundary sits in a layout is in [Architecture](03-architecture.md).

## 24. Importing through a pre-release path

**New in v4.** Pre-release builds of v4 exposed these modules as `effect/unstable/<module>`. The `unstable` segment was dropped before 4.0.0, with no compatibility export (upstream `MIGRATION.md`). Resolving the old specifier on 4.0.0 fails: Node gives `ERR_MODULE_NOT_FOUND` for `effect/unstable/http`, and `tsc` gives `Cannot find module 'effect/unstable/http'`. Older posts and some migration material still show the old form.

```ts
// ❌ Pre-release path. Does not resolve.
import { HttpRouter } from "effect/unstable/http"
```

```ts
// ✅ The 4.0.0 specifier. Unstable exports are still unstable; the path just no longer says so.
import * as HttpRouter from "effect/http/HttpRouter"
```

## What changed in the v3 list

- **v3's "Effect.Service is experimental".** Dropped, the only v3 entry with no v4 counterpart. v3's `Service` on `Effect`, `Tag` on `Context` and `Effect`, and `GenericTag` are not exports of 4.0.0, and `Context.Service` is untagged (stable). The remaining service trap is [11](#11-service-key-collisions).
- **v3's "`Layer.fresh` overuse, or expecting fresh when it is memoized".** Kept but restated: sharing now crosses `provide` calls, and `local: true` is new. See [9](#9-layer-sharing-fresh-local-and-nested-provides).

Renames in general are not a pitfall of their own: for one symbol, ask upstream's `migration/v3-to-v4.md` or [Coming from v3](01-coming-from-v3.md).

## Diagnosing a messy E or R

The characteristic Effect type error appears at the provide or run site: `R` will not reach `never`, or `E` contains something you did not put there. Read the channels, not the wall of text.

**1. Name the three channels.** The `Effect` module has the type-level accessors. On 4.0.0 the requirement accessor is `Effect.Services` (v3's `Context` accessor has no counterpart in 4.0.0):

```ts
type A = Effect.Success<typeof program>
type E = Effect.Error<typeof program>
type R = Effect.Services<typeof program> // hover: the services still missing
```

An unresolved requirement reads like this at the run site, and the type named last is the service you forgot:

```
Argument of type 'Effect<string, never, Database>' is not assignable to parameter of type 'Effect<string, never, never>'.
  Type 'Database' is not assignable to type 'never'.
```

**2. Bisect with annotations.** Annotate an intermediate step with the type you believe it has. The error moves to the first step where belief and reality diverge:

```ts
const step1: Effect.Effect<User, UserNotFound, UserRepo> = fetchUser(id)
const step2: Effect.Effect<string, UserNotFound, UserRepo> = step1.pipe(Effect.map((u) => u.name))
```

**3. Read the leak.** For a layer, print its three parameters: `Layer<ROut, E, RIn>`. A layer whose `RIn` is not `never` still needs something; one whose `ROut` lacks a service did not provide it. Common causes on 4.0.0, in the order they occur:

| Symptom | Usual cause |
| --- | --- |
| `R` contains a service you thought you provided | The layer you provided does not output it: read its `ROut`. `Layer.provide` hides the provider from the layer it feeds (see 10) |
| `R` contains `Scope` | A scoped effect never got `Effect.scoped`. A layer built with `Layer.effect` removes `Scope` itself, so this is an effect, not a layer (see 8) |
| `E` gained `UnknownError` | `Effect.try` or `Effect.tryPromise` without a `catch` mapping to a domain error (v3 called it `UnknownException`) |
| `E` gained `SchemaError` | An unhandled `Schema.decodeUnknownEffect` (v3's `ParseError`) |
| `E` gained `NoSuchElementError` | `Effect.fromOption` of a `None`, or another Option bridge |
| `E` is `never` but failures still happen | Something became a defect (`orDie`, `Effect.die`, a throw); read the `Cause`'s `reasons`, not `E` (see 6, 19) |
| `Type 'Ref<…>' must have a '[Symbol.iterator]()' method` | You yielded a `Ref`, `Deferred` or `Fiber` directly; use `Ref.get`, `Deferred.await`, `Fiber.join` (see 18) |
| `Property '[TypeId]' is missing in type 'None<…>'` | You passed an `Option` or `Result` where an `Effect` goes (see 18) |
| `Cannot find module 'effect/unstable/…'` | A pre-release import path (see 24) |
| Types pass but the run dies with `Service not found: <key>` | A cast hid an unprovided service (see 14). Colliding keys do not do this: they resolve silently to the wrong value (see 11) |

## See also

- [Coming from v3](01-coming-from-v3.md) for the concept shifts, and upstream's `migration/` guides for a given symbol
- [Stability](02-stability.md) · [Architecture](03-architecture.md)
- The bundled guide: `AGENTS.md` and `ai-docs/` in the `effect` package
