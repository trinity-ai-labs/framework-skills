# Concurrency & Fibers

## Contents

- [The fiber model](#the-fiber-model)
- [Forking: `fork` and friends](#forking-fork-and-friends)
- [Structured concurrency & automatic supervision](#structured-concurrency-automatic-supervision)
- [Inspecting & controlling fibers](#inspecting-controlling-fibers)
- [Prefer high-level operators over raw fibers](#prefer-high-level-operators-over-raw-fibers)
- [Racing](#racing)
- [Timeouts](#timeouts)
- [The interruption model](#the-interruption-model)
- [Managing dynamic sets of fibers](#managing-dynamic-sets-of-fibers)
- [When do you actually need raw fibers?](#when-do-you-actually-need-raw-fibers)
- [See also](#see-also)

---


When you reach for this: you want to do things at the same time — run N requests in parallel, race a task against a timeout, run a background worker, or cancel work that's no longer needed. Effect's concurrency is built on **fibers** (lightweight, cooperatively-scheduled virtual threads) with **structured concurrency** and **safe, automatic interruption**. The headline: you almost never manage fibers by hand. Reach for `Effect.all`, `Effect.forEach`, `Effect.race`, and `Effect.timeout` first — they fork, supervise, and clean up fibers for you.

All APIs verified against the `effect` v3 source (`packages/effect/src/Effect.ts`, `Fiber.ts`, `FiberHandle.ts`, `FiberSet.ts`, `FiberMap.ts`).

## The fiber model

A **fiber** is Effect's unit of concurrency: a lightweight virtual thread, multiplexed M:N onto the JS event loop. You can have hundreds of thousands of fibers. They are **cooperative** — a fiber yields at effect boundaries (each `yield*`, each combinator step), which is also where **interruption** is observed. There is no preemption mid-synchronous-block.

Two consequences:
- A tight synchronous loop with no effect boundaries won't yield or respond to interruption. Break it up (e.g. with `Effect.yieldNow`) if it must be cancellable.
- Because fibers yield at boundaries, interruption is *deterministic* and *safe*: finalizers (see resources reference) always get a chance to run.

## Forking: `fork` and friends

Forking starts an effect on a new fiber and returns a `Fiber` handle immediately (it does not wait).

```ts
import { Effect, Fiber } from "effect"

const program = Effect.gen(function* () {
  //   ┌─── RuntimeFiber<number, never>
  //   ▼
  const fiber = yield* Effect.fork(longTask)
  // ... do other work concurrently ...
  const result = yield* Fiber.join(fiber) // wait for it, propagating failures
  return result
})
declare const longTask: Effect.Effect<number>
```

The fork family — what each one ties the child's lifetime to:

| Function | Child fiber lives until… | Requires `Scope`? |
| --- | --- | --- |
| `Effect.fork(self)` | the **parent fiber** ends (auto-supervised) | no |
| `Effect.forkScoped(self)` | the enclosing **`Scope`** closes | yes (`Scope`) |
| `Effect.forkIn(self, scope)` | the given **`scope`** closes | no |
| `Effect.forkDaemon(self)` | the **global** scope (app) — detached from parent | no |
| `Effect.forkAll(effects)` | forks many, returns one composite `Fiber` | no |

```ts
import { Effect, Schedule } from "effect"

// Background worker that should die with its parent — the default, structured choice:
yield* Effect.fork(pollQueue)

// Background worker that should outlive the parent fiber but die with the scope:
const program = Effect.scoped(
  Effect.gen(function* () {
    yield* Effect.forkScoped(heartbeat) // stops when this scope closes
    yield* doWork
  })
)

// Truly detached daemon (be careful — nothing supervises it but the app):
yield* Effect.forkDaemon(metricsFlusher)

declare const pollQueue: Effect.Effect<never>
declare const heartbeat: Effect.Effect<never>
declare const doWork: Effect.Effect<void>
declare const metricsFlusher: Effect.Effect<never>
```

`forkIn` is for "fork into a *specific* outer scope" — e.g. a child fiber that must outlive an inner scope but be torn down with an outer one:

```ts
import { Effect } from "effect"

const program = Effect.scoped(
  Effect.gen(function* () {
    const outer = yield* Effect.scope // the current (outer) scope
    yield* Effect.scoped(
      Effect.gen(function* () {
        // forked into `outer`, so it survives this inner scope closing:
        yield* Effect.forkIn(child, outer)
        yield* Effect.sleep("1 second")
      })
    )
    yield* Effect.sleep("3 seconds") // child still running here
  })
) // child interrupted when outer scope closes
declare const child: Effect.Effect<never>
```

`forkAll` forks an iterable and gives you a single composite fiber:

```ts
import { Effect, Fiber } from "effect"
const fiber = yield* Effect.forkAll([taskA, taskB, taskC])
const results = yield* Fiber.join(fiber) // Array of results, in order
// Effect.forkAll(effects, { discard: true }) → Effect<void> (don't keep results)
declare const taskA: Effect.Effect<number>
declare const taskB: Effect.Effect<number>
declare const taskC: Effect.Effect<number>
```

## Structured concurrency & automatic supervision

`Effect.fork` creates a **child** of the current fiber. Children are automatically supervised: **when the parent fiber terminates (success, failure, or interruption), all its still-running children are interrupted.** No leaked background fibers, no manual bookkeeping. This is structured concurrency.

```ts
import { Effect } from "effect"

const program = Effect.gen(function* () {
  yield* Effect.fork(Effect.never) // would run forever...
  yield* Effect.sleep("100 millis")
  return "done"
}) // ...but it's interrupted automatically when the parent returns "done"
```

This is why `Effect.all` and `Effect.race` are safe: the fibers they fork are children, so any failure or early completion cleanly tears down the rest. Opt out of supervision only with `forkDaemon` (detach to global) or `forkScoped`/`forkIn` (re-tie to a scope).

## Inspecting & controlling fibers

```ts
import { Effect, Fiber } from "effect"

const fiber = yield* Effect.fork(task)

yield* Fiber.join(fiber)        // Effect<A, E> — wait, propagate failure into the current fiber
yield* Fiber.await(fiber)       // Effect<Exit<A, E>> — wait, get the raw Exit (never fails)
const maybe = yield* Fiber.poll(fiber) // Effect<Option<Exit<A, E>>> — None if still running
yield* Fiber.interrupt(fiber)   // Effect<Exit<A, E>> — interrupt & wait for it to finish unwinding
yield* Fiber.interruptFork(fiber) // Effect<void> — fire interruption, don't wait
yield* Fiber.interruptAll([f1, f2]) // interrupt many
declare const task: Effect.Effect<string>
declare const f1: Fiber.Fiber<unknown>
declare const f2: Fiber.Fiber<unknown>
```

- `join` re-raises the fiber's failure into the caller; `await` hands you the `Exit` to inspect.
- `interrupt` waits for finalizers to finish (safe); `interruptFork` returns immediately.

## Prefer high-level operators over raw fibers

Raw fibers are the primitive. In application code, you almost always want a structured combinator instead — it forks, supervises, collects, and interrupts for you.

### `Effect.all` — combine a tuple/struct/iterable

```ts
import { Effect } from "effect"

// Sequential by default:
const seq = Effect.all([taskA, taskB, taskC])

// Concurrent — bounded or unbounded:
const par = Effect.all([taskA, taskB, taskC], { concurrency: "unbounded" })
const limited = Effect.all([taskA, taskB, taskC], { concurrency: 2 })

// Works on structs too (named results):
const struct = Effect.all({ a: taskA, b: taskB }, { concurrency: 2 })
declare const taskA: Effect.Effect<number>
declare const taskB: Effect.Effect<number>
declare const taskC: Effect.Effect<number>
```

`concurrency` accepts `number | "unbounded" | "inherit"` (the `Concurrency` type):
- a **number** — cap N in flight at once,
- **`"unbounded"`** — all at once,
- **`"inherit"`** — use the concurrency of the enclosing region (set via `Effect.withConcurrency`),
- **omitted / default** — sequential.

Other `Effect.all` options: `discard: true` (drop results, return `void`), `mode: "either" | "validate"` (collect all outcomes instead of failing fast). With the default `mode`, the first failure interrupts the rest (fail-fast).

### `Effect.forEach` — map an iterable to effects

```ts
import { Effect } from "effect"

// Process up to 5 ids at a time:
const results = yield* Effect.forEach(ids, (id) => fetchUser(id), {
  concurrency: 5
})

// Run for side effects only, discard results (returns Effect<void>):
yield* Effect.forEach(ids, (id) => indexUser(id), {
  concurrency: "unbounded",
  discard: true
})
declare const ids: ReadonlyArray<string>
declare const fetchUser: (id: string) => Effect.Effect<{ name: string }>
declare const indexUser: (id: string) => Effect.Effect<void>
```

The callback also receives the index: `(a, i) => Effect`. `discard: true` changes the result type to `Effect<void, E, R>`.

❌ Don't fork-and-join by hand for a fan-out:

```ts
const fibers = yield* Effect.forEach(ids, (id) => Effect.fork(fetchUser(id)))
const users = yield* Effect.forEach(fibers, Fiber.join) // unbounded, no error-fast, verbose
```

✅ Do let `forEach` manage concurrency and supervision:

```ts
const users = yield* Effect.forEach(ids, fetchUser, { concurrency: 10 })
```

### `Effect.zip` / `zipWith` with `{ concurrent: true }`

For exactly two effects:

```ts
import { Effect } from "effect"

// Sequential: a then b
const pair = Effect.zip(taskA, taskB)
// Concurrent: a and b at the same time
const parPair = Effect.zip(taskA, taskB, { concurrent: true })
// Combine with a function, concurrently:
const sum = Effect.zipWith(taskA, taskC, (a, c) => a + c, { concurrent: true })
declare const taskA: Effect.Effect<number>
declare const taskB: Effect.Effect<string>
declare const taskC: Effect.Effect<number>
```

## Racing

Run effects concurrently and take the first to complete; the losers are interrupted.

```ts
import { Effect } from "effect"

// First to SUCCEED OR FAIL wins (failure of the winner propagates):
const first = Effect.raceFirst(taskA, taskB)

// First to SUCCEED wins; failures are ignored until only failures remain:
const firstOk = Effect.race(taskA, taskB)
const anyOk = Effect.raceAll([taskA, taskB, taskC]) // iterable

// Full control over both completions:
const custom = Effect.raceWith(taskA, taskB, {
  onSelfDone: (exitA, fiberB) => Fiber.join(fiberB),   // A finished first
  onOtherDone: (exitB, fiberA) => Fiber.interrupt(fiberA) // B finished first
})
declare const taskA: Effect.Effect<number, Error>
declare const taskB: Effect.Effect<number, Error>
declare const taskC: Effect.Effect<number, Error>
```

- `race` — first **success** wins; if all fail, fails with the last error. Losing fibers interrupted.
- `raceAll` — like `race` for an iterable.
- `raceFirst` — first to **settle** (success *or* failure) wins.
- `raceWith` — lowest level; you supply `onSelfDone`/`onOtherDone` callbacks that get each `Exit` and the other `Fiber`.

## Timeouts

Built on racing internally. The timed-out effect is **interrupted** (so its finalizers run).

```ts
import { Effect, Option } from "effect"

// Fail with TimeoutException after the duration:
const a = task.pipe(Effect.timeout("5 seconds"))
//   Effect<A, TimeoutException | E, R>

// Fail with YOUR error on timeout:
const b = task.pipe(
  Effect.timeoutFail({ duration: "5 seconds", onTimeout: () => new SlowError() })
)

// No error — get Option.none() on timeout, Option.some(a) otherwise:
const c = task.pipe(Effect.timeoutOption("5 seconds"))
//   Effect<Option<A>, E, R>

// Map both branches:
const d = task.pipe(
  Effect.timeoutTo({
    duration: "5 seconds",
    onSuccess: (a) => ({ ok: true, value: a }),
    onTimeout: () => ({ ok: false as const })
  })
)
declare const task: Effect.Effect<number, Error>
class SlowError { readonly _tag = "SlowError" }
```

Also `Effect.timeoutFailCause` to die with a custom defect on timeout.

## The interruption model

Interruption is **automatic and safe**. When a fiber is interrupted (parent ended, race lost, timeout, explicit `Fiber.interrupt`), it stops at the next yield point and **runs all pending finalizers** before completing with an interrupted `Exit`. You don't write cancellation tokens; you write finalizers (see resources reference) and they just run.

### Controlling interruptibility

```ts
import { Effect } from "effect"

// Force a region to be interruptible even inside an uninterruptible one:
Effect.interruptible(work)

// Make a region uninterruptible — interruption is deferred until it exits:
Effect.uninterruptible(criticalSection)

// Fine-grained: uninterruptible by default, but `restore` re-opens a window.
// This is the safe pattern for "acquire uninterruptibly, use interruptibly".
const safe = Effect.uninterruptibleMask((restore) =>
  Effect.gen(function* () {
    const resource = yield* acquire          // protected from interruption
    return yield* restore(use(resource)).pipe( // interruptible again
      Effect.ensuring(release(resource))      // always runs
    )
  })
)

// Inverse: interruptible by default, restore re-closes a window.
Effect.interruptibleMask((restore) => Effect.gen(function* () { /* ... */ }))
declare const work: Effect.Effect<void>
declare const criticalSection: Effect.Effect<void>
declare const acquire: Effect.Effect<{ id: number }>
declare const use: (r: { id: number }) => Effect.Effect<string>
declare const release: (r: { id: number }) => Effect.Effect<void>
```

`acquireRelease` (resources reference) uses exactly this masking so acquire/release are uninterruptible while `use` stays cancellable. You rarely need the masks directly — prefer the bracket operators.

### Reacting to interruption: `onInterrupt`

```ts
import { Effect, Console } from "effect"

work.pipe(
  Effect.onInterrupt((interruptors) =>
    Console.log(`interrupted by ${interruptors.size} fiber(s)`)
  )
)
declare const work: Effect.Effect<void>
```

`onInterrupt`'s cleanup runs **only** on interruption (not on normal success/failure), and receives the `HashSet<FiberId>` of interruptors. For "any outcome" use `ensuring`/`onExit` instead.

### `disconnect` — detach from synchronous interruption

`Effect.disconnect(self)` lets the parent's interruption return *immediately* while `self` finishes its interruption (finalizers) in the background, rather than the parent blocking until `self` fully unwinds. Useful when a slow finalizer would otherwise stall a race/timeout. Niche — reach for it only when finalizer latency is a measured problem.

## Managing dynamic sets of fibers

When the *number* of background fibers isn't known statically — a fiber per WebSocket connection, per subscription, per key — use these scope-bound containers. Each is created in a `Scope`; when the scope closes, every fiber it holds is interrupted. All three have `make()`, `run`, `clear`, and `awaitEmpty`.

### `FiberHandle` — at most ONE fiber

Holds a single fiber; setting a new one interrupts the previous. Good for "latest wins" (e.g. a debounced job, the current in-flight request for a widget).

```ts
import { Effect, FiberHandle } from "effect"

const program = Effect.gen(function* () {
  const handle = yield* FiberHandle.make()
  yield* FiberHandle.run(handle, job("first"))
  yield* FiberHandle.run(handle, job("second")) // interrupts "first"
}).pipe(Effect.scoped)
declare const job: (label: string) => Effect.Effect<void>
```

### `FiberSet` — an unkeyed COLLECTION of fibers

Holds many fibers; each completes and removes itself. Good for "spawn one per event, all torn down together".

```ts
import { Effect, FiberSet } from "effect"

const program = Effect.gen(function* () {
  const set = yield* FiberSet.make()
  yield* FiberSet.run(set, handleConn("a"))
  yield* FiberSet.run(set, handleConn("b"))
  // both interrupted when the scope closes
}).pipe(Effect.scoped)
declare const handleConn: (id: string) => Effect.Effect<void>
```

### `FiberMap` — a KEYED collection of fibers

Holds one fiber per key; `run`/`set` with an existing key interrupts the old fiber for that key. Good for "one worker per user/room/job id, replaceable".

```ts
import { Effect, FiberMap } from "effect"

const program = Effect.gen(function* () {
  const map = yield* FiberMap.make<string>()
  yield* FiberMap.run(map, "user-1", watch("user-1"))
  yield* FiberMap.run(map, "user-2", watch("user-2"))
  yield* FiberMap.run(map, "user-1", watch("user-1")) // replaces user-1's fiber
}).pipe(Effect.scoped)
declare const watch: (id: string) => Effect.Effect<void>
```

`FiberMap.set` also takes `{ onlyIfMissing, propagateInterruption }`. All three containers also expose `makeRuntime`/`runtime` for forking effects that need a context.

## When do you actually need raw fibers?

Rarely. Decision order:
1. Fan-out a collection → `Effect.forEach({ concurrency })`.
2. Combine a fixed set → `Effect.all` / `Effect.zip({ concurrent: true })`.
3. First-to-finish / fallback / timeout → `race` / `raceAll` / `timeout`.
4. Long-lived background work → `forkScoped` (tied to a scope) or `Layer.scoped` for app-lifetime workers.
5. Dynamic, replaceable background fibers → `FiberHandle` / `FiberSet` / `FiberMap`.
6. Only then, if none fit, raw `fork` + `Fiber.join`/`interrupt`.

❌ Don't `runPromise` inside an effect to "go parallel", and don't track fibers in a mutable array. ✅ Do use the structured operators — they give you supervision, fail-fast, and guaranteed cleanup for free.

## See also

- [06-resources-scope.md](06-resources-scope.md) — `Scope`, finalizers, `acquireRelease`; why interruption is safe (finalizers always run) and how `forkScoped`/`forkIn` tie fibers to scopes.
- [04-errors.md](04-errors.md) — how failures from forked fibers surface via `join`, `Cause`, and `Exit`.
