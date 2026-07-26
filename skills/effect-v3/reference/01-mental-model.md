# Mental Model: Effect<A, E, R>

The three-channel type is the foundation of everything in Effect. Understand it once and the rest follows.

## The Three Channels

```ts
import { Effect } from "effect"

//              ┌─── A: the success value type
//              │      ┌─── E: the typed error type
//              │      │       ┌─── R: the requirements (services needed)
//              ▼      ▼       ▼
type MyEffect = Effect.Effect<number, Error, never>
```

| Channel | Variance | Meaning |
|---------|----------|---------|
| `A` (Success) | covariant (`out A`) | The value produced on the happy path |
| `E` (Error) | covariant (`out E`) | Typed, recoverable failures |
| `R` (Requirements) | covariant (`out R`) | Services that must be provided before the effect can run |

`R = never` means the effect has no unmet dependencies — it is self-contained and can be run immediately.

## Effects Are Lazy Descriptions, Not Eager Computations

```ts
import { Effect } from "effect"

// This does NOT execute anything. It is a description.
const program = Effect.sync(() => {
  console.log("hello")
  return 42
})

// Nothing happens until you explicitly run it.
const result = Effect.runSync(program) // executes here
```

Compare with a `Promise`: constructing `new Promise((resolve) => { sideEffect() })` runs `sideEffect` immediately. An `Effect` does not. This is called **referential transparency** — you can pass, store, compose, and duplicate an `Effect` value without triggering execution.

```ts
import { Effect } from "effect"

// Referential transparency: each yield* re-executes the description
const increment = Effect.sync(() => {
  let n = 0
  return ++n
})

const program = Effect.gen(function* () {
  const a = yield* increment // executes, returns 1
  const b = yield* increment // executes again, returns 1 (fresh closure)
  return [a, b]
})
```

## Why Effect Over try/catch + Promise

| Concern | try/catch + Promise | Effect |
|---------|--------------------|----|
| Typed errors | `catch (e: unknown)` | `E` channel — exact error types |
| Dependency tracking | implicit / global | `R` channel — compiler-checked |
| Interruption / cancellation | manual `AbortController` wiring | built-in fiber interruption |
| Composition | imperative nesting | `flatMap`, `gen`, combinators |
| Retry / scheduling | hand-rolled loops | `Effect.retry`, `Schedule` |
| Concurrency | `Promise.all` (untyped) | `Effect.all` with typed errors + concurrency control |

## Why Composition Is the Payoff

Because an effect is a *value* carrying its full type — success, error, and requirements all visible — combining effects never discards information. Join two effects and the result is a third effect whose channels are the union of the parts: errors stay named in `E`, dependencies accumulate in `R`, and resource-safety and interruption propagate through automatically. The compiler tracks the whole as precisely as the pieces.

That uniformity is what makes the standard library universal. Every operator — `retry`, `timeout`, `Effect.all`, `catchTag`, `Effect.scoped` — takes an effect and returns an effect, so the same combinator wraps a one-line query and a thousand-line subsystem with no adapter:

```ts
import { Effect, Schedule } from "effect"

// the same wrappers compose around anything that is an Effect
const resilient = program.pipe(
  Effect.timeout("5 seconds"),
  Effect.retry(Schedule.exponential("100 millis")),
  Effect.provide(DatabaseLive)
)
```

Imperative code loses this at every boundary: a `try/catch` collapses the error type to `unknown`, dependencies leak in as globals or bare imports, and cancellation has to be re-plumbed by hand. Each layer of nesting *erodes* the guarantees. In Effect they *accumulate*.

This is the reason behind **"build descriptions everywhere; run at the edge."** Deferring execution is not a stylistic choice — deferral is precisely what lets a small description become part of a larger one without ceremony. The moment you run an effect, the value collapses into an ordinary side-effecting computation and stops composing. Keep things as `Effect` values for as long as possible; that window is where all the leverage lives. → see [running at the edge](02-creating-running.md).

## The Two Authoring Styles

### Generator style (primary)

Write sequential effect code that reads like `async/await`. Use `yield*` to unwrap an effect's success value. Errors short-circuit automatically and are tracked in the type.

```ts
import { Effect } from "effect"

const fetchUser = (id: number): Effect.Effect<{ name: string }, Error> =>
  Effect.tryPromise({
    try: () => fetch(`/users/${id}`).then((r) => r.json()),
    catch: (e) => new Error(`fetch failed: ${e}`)
  })

const program = Effect.gen(function* () {
  const user = yield* fetchUser(1)   // Error propagates automatically
  const upper = user.name.toUpperCase()
  return upper
})
// Type: Effect.Effect<string, Error, never>
```

### Pipe style (data-last)

Chain operations with `.pipe(...)`. Every combinator has a data-last overload, making it composable in pipelines.

```ts
import { Effect } from "effect"

const program = fetchUser(1).pipe(
  Effect.map((user) => user.name.toUpperCase()),
  Effect.tapError((err) => Effect.log(`Error: ${err.message}`))
)
```

### When to use each

| Situation | Prefer |
|-----------|--------|
| Sequential steps, if/else branches, loops, local variables | `gen` |
| Short transformations on a single value | `.pipe` with `map` / `tap` |
| Library-facing APIs (composable middleware) | `.pipe` (data-last is pipeable) |
| Mixing sync and async steps | `gen` |

You can freely mix both. A `gen` block can `.pipe` its result; a pipe chain can call `flatMap(x => Effect.gen(...))`.

## Variance in Practice

All three channels are marked `out` (covariant) in v3:

```ts
export interface Effect<out A, out E = never, out R = never> { ... }
```

**Practical implications:**

- **`A` and `E` are covariant**: an `Effect<string, never>` is assignable to `Effect<string | number, never>`. You can widen the success and error types upward.
- **`R` is covariant**: `Effect<A, E, DatabaseService>` is a subtype of `Effect<A, E, never>` only after `DatabaseService` is provided. The compiler accumulates requirements via union — composing two effects with different `R` channels gives you `R1 | R2` in the combined effect.

```ts
import { Effect, Context } from "effect"

class Db extends Effect.Tag("Db")<Db, { query: (sql: string) => Effect.Effect<unknown> }>() {}
class Cache extends Effect.Tag("Cache")<Cache, { get: (key: string) => Effect.Effect<string | null> }>() {}

// R = Db | Cache — both requirements are tracked
const combined = Effect.gen(function* () {
  const db = yield* Db
  const cache = yield* Cache
  return { db, cache }
})
// Type: Effect.Effect<{ db: ..., cache: ... }, never, Db | Cache>
```

## The `E = never` and `R = never` Defaults

Both default to `never` in the interface signature, meaning "no error" and "no requirements":

```ts
// Equivalent ways to annotate a self-contained, infallible effect:
type T1 = Effect.Effect<string>
type T2 = Effect.Effect<string, never>
type T3 = Effect.Effect<string, never, never>
```

## Common Mistakes

```ts
import { Effect } from "effect"

// ❌ Running effects inside constructors defeats the lazy model
const bad = Effect.sync(() => {
  return Effect.runSync(someOtherEffect) // nested run — never do this
})

// ✅ Compose effects with flatMap / gen instead
const good = Effect.flatMap(someOtherEffect, (value) => Effect.succeed(value + 1))
```

```ts
import { Effect } from "effect"

// ❌ Ignoring the error channel by casting
const risky = fetchUser(1) as Effect.Effect<{ name: string }, never>

// ✅ Handle or propagate errors explicitly
const safe = fetchUser(1).pipe(
  Effect.catchAll((err) => Effect.succeed({ name: "anonymous" }))
)
```

## See also

- [02-creating-running.md](02-creating-running.md) — constructors and running effects at the edge
- [03-combinators.md](03-combinators.md) — `map`, `flatMap`, `all`, `forEach`, and control flow
