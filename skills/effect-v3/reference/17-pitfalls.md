# Pitfalls & anti-patterns

> **When you reach for this:** when something "doesn't run," runs once when you expected many, deadlocks, leaks a connection, or a test hangs on a real timer. These are the mistakes that bite people coming from Promises/OOP. Each has the fix next to it.

---

## Contents

- [1. Forgetting effects are lazy descriptions](#1-forgetting-effects-are-lazy-descriptions)
- [2. `Effect.all` / `forEach` are SEQUENTIAL by default](#2-effectall-foreach-are-sequential-by-default)
- [3. Running effects inside effects](#3-running-effects-inside-effects)
- [4. Throwing / try-catch / async-await inside `gen`](#4-throwing-try-catch-async-await-inside-gen)
- [5. Swallowing errors silently](#5-swallowing-errors-silently)
- [6. `catchTag` does not catch defects](#6-catchtag-does-not-catch-defects)
- [7. Real timers, `Date.now`, and `Math.random`](#7-real-timers-datenow-and-mathrandom)
- [8. Resources without a scope](#8-resources-without-a-scope)
- [9. `Layer.fresh` overuse → double-acquire; or expecting fresh when it's memoized](#9-layerfresh-overuse-double-acquire-or-expecting-fresh-when-its-memoized)
- [10. `provide` vs `provideMerge`](#10-provide-vs-providemerge)
- [11. Tag key collisions](#11-tag-key-collisions)
- [12. Long synchronous loops block interruption](#12-long-synchronous-loops-block-interruption)
- [13. Not decoding untrusted input](#13-not-decoding-untrusted-input)
- [14. `as any` / casting to dodge the `R` or `E` channel](#14-as-any-casting-to-dodge-the-r-or-e-channel)
- [15. Reinventing primitives](#15-reinventing-primitives)
- [16. Over-using `gen` for trivial transforms](#16-over-using-gen-for-trivial-transforms)
- [17. `Effect.Service` is `@experimental`](#17-effectservice-is-experimental)
- [Diagnosing a messy `E` or `R`](#diagnosing-a-messy-e-or-r)
- [See also](#see-also)


## 1. Forgetting effects are lazy descriptions

An `Effect` does nothing until run. Building one has no side effects.

```ts
// ❌ Expecting this to log — it never runs. `program` is just a value.
const program = Effect.log("hello")
// ...nothing happens

// ✅ Compose it into something that runs, or run it at the edge.
yield* program                         // inside a gen
Effect.runFork(program)                // at the entry point
```

A subtler version: a `gen` block that *builds* an effect but never `yield*`s it.

```ts
// ❌ The inner effect is constructed and dropped on the floor.
Effect.gen(function* () {
  saveUser(user)            // returns Effect<...> — discarded, never executes
})

// ✅ Yield it.
Effect.gen(function* () {
  yield* saveUser(user)
})
```

---

## 2. `Effect.all` / `forEach` are SEQUENTIAL by default

The single most common surprise. Default concurrency is **1** — effects run one after another.

```ts
// ❌ Runs the 100 fetches one at a time.
const results = yield* Effect.all(ids.map(fetchUser))

// ✅ Opt into concurrency explicitly.
const results = yield* Effect.all(ids.map(fetchUser), { concurrency: 10 })
const all     = yield* Effect.all(ids.map(fetchUser), { concurrency: "unbounded" })

// Same for forEach:
yield* Effect.forEach(ids, fetchUser, { concurrency: 10 })
```

See [Concurrency & Fibers](07-concurrency-fibers.md). Pick a bounded number for anything hitting a real resource; `"unbounded"` only when the work is cheap or already rate-limited.

---

## 3. Running effects inside effects

Nesting `runSync`/`runPromise` throws away context, the error channel, interruption, and tracing.

```ts
// ❌ Never run inside business logic.
const handler = Effect.sync(() => {
  const user = Effect.runSync(fetchUser(id))   // loses E, R, interruption
  return user
})

// ✅ Stay in the Effect world; run once at the top.
const handler = Effect.gen(function* () {
  const user = yield* fetchUser(id)
  return user
})
```

If your `R` channel won't reach `never` at the entry point, that's the real problem — wire the missing dependency, don't reach for a nested run or a cast.

---

## 4. Throwing / try-catch / async-await inside `gen`

The generator is not an `async` function. Don't throw, don't `await`, don't `try/catch` around yields for control flow.

```ts
// ❌
Effect.gen(function* () {
  try {
    const u = yield* fetchUser(id)
  } catch (e) { /* this is not how errors flow */ }
})

// ✅ Errors are in the E channel — handle with combinators.
fetchUser(id).pipe(
  Effect.catchTag("UserNotFound", () => Effect.succeed(defaultUser))
)
```

To bring a throwing/async API in, wrap it: `Effect.try`, `Effect.tryPromise`, `Effect.async`.

---

## 5. Swallowing errors silently

`catchAll(() => Effect.succeed(fallback))` is the Effect equivalent of an empty `catch {}`.

```ts
// ❌ Loses the failure entirely — no log, no metric, no signal.
fetchUser(id).pipe(Effect.catchAll(() => Effect.succeed(null)))

// ✅ Handle the specific case you know about; let the rest propagate.
fetchUser(id).pipe(
  Effect.catchTag("UserNotFound", () => Effect.succeed(null))
)
// or recover but record it:
fetchUser(id).pipe(
  Effect.tapError((e) => Effect.logError(e)),
  Effect.catchAll(() => Effect.succeed(null))
)
```

Catch *tags*, not *everything*. Reserve `catchAll` for a true boundary where you genuinely handle all cases.

---

## 6. `catchTag` does not catch defects

`catch*` for typed errors only sees the `E` channel. A defect (`Effect.die`, a thrown exception in `Effect.sync`, a bug) flows through `Cause` as a `Die` and is **not** caught by `catchTag`/`catchAll`.

```ts
// ❌ Won't catch a defect.
risky.pipe(Effect.catchAll(() => recover))   // only typed failures

// ✅ For defects use the cause-level handlers.
risky.pipe(Effect.catchAllCause((cause) => ...))
risky.pipe(Effect.catchAllDefect((defect) => ...))
```

This is by design: defects should usually crash. See [Error management](04-errors.md).

---

## 7. Real timers, `Date.now`, and `Math.random`

Reaching for the platform directly makes code non-deterministic and untestable, and `setTimeout` isn't interruptible.

```ts
// ❌
yield* Effect.sync(() => new Promise((r) => setTimeout(r, 1000)))
const t = Date.now()
const x = Math.random()

// ✅ Use Effect's services — interruptible AND controllable with TestClock.
yield* Effect.sleep("1 second")
const t = yield* Clock.currentTimeMillis
const x = yield* Random.next
```

Code written this way tests *instantly* under `TestClock` (see [Testing](15-testing.md) and [Scheduling & time](09-scheduling-time.md)).

---

## 8. Resources without a scope

`acquireRelease` registers a finalizer in the *current scope*. If there's no scope, `R` includes `Scope` and the type won't collapse — and if you bypass that with a manual run, the resource leaks.

```ts
// ✅ Give it a scope and the finalizer runs on success/failure/interruption.
Effect.acquireRelease(open, close).pipe(
  Effect.flatMap(use),
  Effect.scoped                       // closes the scope here
)

// ✅ For app-lifetime resources (pools, servers), put them in a scoped layer.
Layer.scoped(Pool, acquirePool)
```

See [Resources & Scope](06-resources-scope.md). Don't hand-roll try/finally — finalizers are interruption-safe; `finally` is not.

---

## 9. `Layer.fresh` overuse → double-acquire; or expecting fresh when it's memoized

Layers are **built once and shared by default**. Two traps:

```ts
// ❌ Adding Layer.fresh "to be safe" — now the pool/socket is acquired TWICE.
Layer.merge(DbLive, Layer.fresh(DbLive))

// ❌ Expecting two independent instances from the same reference — you get one.
//    (sharing is correct here; just know it's happening)
```

Rely on memoization: define `DbLive` once, reference it everywhere, compose. Use `Layer.fresh` only when you deliberately need a *separate* instance + its own resources. See [Context, Services & Layers](05-context-layers.md).

---

## 10. `provide` vs `provideMerge`

```ts
// provide:      deps satisfy inputs but are HIDDEN from the output.
RepoLive.pipe(Layer.provide(DbLive))        // ROut = Repo
// provideMerge: deps satisfy inputs AND stay in the output.
RepoLive.pipe(Layer.provideMerge(DbLive))   // ROut = Repo | Database
```

❌ Reaching for `provideMerge` everywhere leaks internal services into your public layer surface (callers start depending on `Database` directly). ✅ Use `provide` for internal plumbing; `provideMerge` only when the dependency is genuinely part of what you expose.

---

## 11. Tag key collisions

Context is a map keyed by the tag's **string id**. Two tags with the same key are the same slot.

```ts
// ❌ Bare, ungeneric keys clash across modules.
Context.GenericTag<Config>("Config")

// ✅ Namespace every key.
Context.GenericTag<Config>("App/Config")
class UserRepo extends Effect.Service<UserRepo>()("@myorg/UserRepo", { ... }) {}
```

---

## 12. Long synchronous loops block interruption

Fibers are cooperative. A tight CPU loop inside one `Effect.sync` never yields, so it can't be interrupted and starves other fibers.

```ts
// ❌ One giant synchronous block — uninterruptible.
Effect.sync(() => { for (let i = 0; i < 1e9; i++) heavy(i) })

// ✅ Break it into effects so the runtime can interrupt/schedule between steps.
Effect.forEach(Chunk.range(0, n), (i) => Effect.sync(() => heavy(i)), { discard: true })
// or insert Effect.yieldNow() periodically in a gen loop.
```

---

## 13. Not decoding untrusted input

`JSON.parse` gives you `any`. Trusting it defeats the type system at the most important boundary.

```ts
// ❌
const body = JSON.parse(raw) as CreateUser

// ✅ Decode with a Schema — typed value or a ParseError you can handle.
const body = yield* Schema.decodeUnknown(CreateUser)(JSON.parse(raw))
```

See [Schema & Config](11-schema.md). Decode at the edge; trust the type inside.

---

## 14. `as any` / casting to dodge the `R` or `E` channel

A non-`never` `R` at the entry point, or an `E` you don't want to handle, is the compiler doing its job. Casting silences the one tool that prevents the bug.

```ts
// ❌ "It compiles now."
Effect.runPromise(program as Effect.Effect<string>)

// ✅ Provide the dependency / handle the error. Then the cast isn't needed.
Effect.runPromise(program.pipe(Effect.provide(MainLive)))
```

---

## 15. Reinventing primitives

Effect's stdlib already has the thing. Before hand-rolling:

| You wrote | Use instead |
| --- | --- |
| a retry loop with `setTimeout` | `Effect.retry(schedule)` ([scheduling](09-scheduling-time.md)) |
| a debounce/throttle by hand | `Stream.debounce`/`throttle` ([streams](10-streams.md)) |
| a mutex with booleans | `Effect.makeSemaphore` ([state](08-state-coordination.md)) |
| shared mutable state via closure | `Ref` / `SynchronizedRef` |
| a one-shot "wait for X" flag | `Deferred` |
| manual `Promise.all` + error juggling | `Effect.all({ concurrency })` |
| `try/finally` cleanup | `acquireRelease` / `ensuring` |
| a hand-written config parser | `Config` + `Schema` |

---

## 16. Over-using `gen` for trivial transforms

`gen` is for sequential/branching logic. A single map doesn't need it.

```ts
// ❌ Ceremony for one transform.
Effect.gen(function* () { const u = yield* fetchUser(id); return u.name })

// ✅
fetchUser(id).pipe(Effect.map((u) => u.name))
```

Conversely, don't build deep `.pipe(flatMap(flatMap(flatMap(...))))` pyramids — that's what `gen` is for. See [Mental model](01-mental-model.md) for when to use each.

---

## 17. `Effect.Service` is `@experimental`

It's the recommended, widely-used pattern — but the source marks it `@experimental` ("might be up for breaking changes"). Pin your Effect version, and know that the `Context.Tag` class pattern is the stable fallback if you're publishing a long-lived library. See [Context, Services & Layers](05-context-layers.md).

---

## Diagnosing a messy `E` or `R`

The characteristic Effect type error is a wall of text at the *provide* site: `R` won't collapse to `never`, or the error union has something in it you didn't put there. Don't read the wall — interrogate the type.

**1. Extract the three channels and hover them.** The `Effect` namespace exposes type-level accessors, so you can name each channel and let the editor print it:

```ts
import { Effect } from "effect"

type A = Effect.Effect.Success<typeof program>
type E = Effect.Effect.Error<typeof program>
type R = Effect.Effect.Context<typeof program>
//   ^? hover: exactly which services are still missing
```

`R` is the one that matters most — it names the tag you forgot to provide, which the provide-site error usually buries under layer generics.

**2. Bisect the pipeline with annotations.** Annotate an intermediate step with the type you *believe* it has; the error moves to the first step where belief and reality diverge:

```ts
const step1: Effect.Effect<User, UserNotFound, UserRepo> = fetchUser(id)
const step2: Effect.Effect<Invoice, UserNotFound, UserRepo> = step1.pipe(/* … */)
//                                  ^ the error surfaces HERE if this step
//                                    smuggles in a service or an error type
```

**3. Read the leak's shape.** Common causes, in the order they actually happen:

| Symptom | Usual cause |
|---|---|
| `R` contains a tag you thought you provided | Provided into a layer whose `RIn` was already `never` — the provide was a no-op (see [Context, Services & Layers](05-context-layers.md)) |
| `R` contains `Scope` | A scoped effect never got `Effect.scoped` or `Layer.scoped` |
| `R` contains a *duplicate-looking* tag | Two distinct tags with the same identifier string, or two copies of `effect` in `node_modules` |
| `E` gained `UnknownException` | `Effect.tryPromise`/`Effect.try` without a `catch` mapping into a domain error |
| `E` gained `ParseError` | An un-caught `Schema.decodeUnknown` |
| `E` became `never` but failures still happen | Something was turned into a defect (`orDie`, `Effect.die`, a thrown exception) — look at the `Cause`, not `E` |

**4. Never silence it with `as any`.** Casting to close the channel moves a compile-time failure to runtime, where an unprovided service becomes a defect on the first request. See pitfall 14 above.

---

## See also

- [Architecture](16-architecture.md) — the positive patterns these anti-patterns violate
- [Mental model](01-mental-model.md) · [Error management](04-errors.md) · [Context, Services & Layers](05-context-layers.md)
- [Concurrency & Fibers](07-concurrency-fibers.md) · [Resources & Scope](06-resources-scope.md) · [Testing](15-testing.md)
