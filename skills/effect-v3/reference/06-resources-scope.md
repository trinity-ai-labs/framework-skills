# Resource Management & Scope

## Contents

- [The Scope concept](#the-scope-concept)
- [`Effect.acquireRelease` — the building block](#effectacquirerelease-the-building-block)
- [`Effect.acquireUseRelease` — bracket in one call](#effectacquireuserelease-bracket-in-one-call)
- [`Effect.acquireReleaseInterruptible`](#effectacquirereleaseinterruptible)
- [`Effect.addFinalizer` — register cleanup imperatively](#effectaddfinalizer-register-cleanup-imperatively)
- [`ensuring`, `onError`, `onExit` — finalizers scoped to one effect](#ensuring-onerror-onexit-finalizers-scoped-to-one-effect)
- [`Effect.scoped` — provide & close a fresh scope](#effectscoped-provide-close-a-fresh-scope)
- [Finalizer ordering: LIFO, and execution strategy](#finalizer-ordering-lifo-and-execution-strategy)
- [Manual scope: `Scope.make` / `extend` / `close`](#manual-scope-scopemake-extend-close)
- [Scoped resources in layers: `Layer.scoped`](#scoped-resources-in-layers-layerscoped)
- [The bracket pattern, summarized](#the-bracket-pattern-summarized)
- [See also](#see-also)

---


When you reach for this: you have a resource that must be released — a file handle, DB connection, socket, lock, subscription, spawned process — and you need that release to run no matter how the using code ends (success, failure, defect, or interruption). Effect's answer is the `Scope`: a value that collects finalizers and runs them when it closes. `acquireRelease` and friends register finalizers into the ambient scope; `Effect.scoped` provides a fresh scope and closes it. This is the bracket pattern, made composable.

All APIs verified against the `effect` v3 source (`packages/effect/src/Effect.ts`, `Scope.ts`, `Layer.ts`).

## The Scope concept

A `Scope` is a dynamic collection of finalizers. Closing the scope runs every finalizer that was added to it, in **LIFO order** (reverse of acquisition), passing each the `Exit` value the scope closed with. Finalizers always run — on success, on failure, AND on interruption.

Any effect that needs to register a finalizer carries `Scope` in its requirements channel (`R`). You see this in the type:

```ts
import { Effect, Scope } from "effect"

//      ┌─── Effect<MyResource, Error, Scope>  ← needs a Scope
//      ▼
const resource = Effect.acquireRelease(acquire, release)
```

That `Scope` requirement is discharged by `Effect.scoped` (or a `Layer.scoped`, or by manually providing one). You almost never construct or close a `Scope` by hand — you let `Effect.scoped` and the `acquireRelease` family manage it.

```ts
// The Scope interface (Scope.ts) — you rarely touch these methods directly:
interface Scope {
  readonly strategy: ExecutionStrategy // sequential (default) or parallel finalizers
  // internal: fork(strategy), addFinalizer(finalizer)
}
interface CloseableScope extends Scope {
  // internal: close(exit) — runs all finalizers
}
```

## `Effect.acquireRelease` — the building block

```ts
import { Effect, Console } from "effect"

interface DbConn {
  readonly query: (sql: string) => Effect.Effect<unknown>
  readonly close: () => Promise<void>
}

declare const openConn: () => Promise<DbConn>

//      ┌─── Effect<DbConn, never, Scope>
//      ▼
const conn = Effect.acquireRelease(
  // acquire: runs uninterruptibly
  Effect.promise(() => openConn()),
  // release: (resource, exit) => Effect — also uninterruptible, runs on scope close
  (db, exit) =>
    Effect.promise(() => db.close()).pipe(
      Effect.zipRight(Console.log(`closed (${exit._tag})`))
    )
)
```

Signature (data-first and data-last both exist):

```ts
acquireRelease(
  acquire: Effect<A, E, R>,
  release: (a: A, exit: Exit<unknown, unknown>) => Effect<X, never, R2>
): Effect<A, E, Scope | R | R2>
```

Key guarantees:
- **`acquire` is uninterruptible.** You never end up having acquired the resource without registering its finalizer.
- **`release` is uninterruptible** and `never`-fails (`E = never`). A finalizer that could fail or be interrupted would defeat the point. Recover/log inside it.
- The finalizer is added to the **ambient scope**, so it runs when that scope closes — not when `acquire` returns.

❌ Don't release manually in a `finally`-style chain — interruption between use and release leaks the resource:

```ts
const leaky = Effect.gen(function* () {
  const db = yield* Effect.promise(() => openConn())
  yield* useDb(db)                       // interruption here skips the close
  yield* Effect.promise(() => db.close())
})
```

✅ Do bind acquisition to release with `acquireRelease`:

```ts
const safe = Effect.gen(function* () {
  const db = yield* conn // finalizer registered on the scope
  yield* useDb(db)
}) // close runs on scope exit, even under interruption
declare const useDb: (db: DbConn) => Effect.Effect<void>
```

## `Effect.acquireUseRelease` — bracket in one call

When acquire/use/release are all known up front, this is the classic bracket. It manages the scope for you, so the result has **no `Scope` requirement**:

```ts
import { Effect, Console } from "effect"

//      ┌─── Effect<void, never, never>
//      ▼
const program = Effect.acquireUseRelease(
  Effect.promise(() => openConn()),          // acquire
  (db) => useDb(db),                          // use — interruptible
  (db, exit) => Effect.promise(() => db.close()) // release — uninterruptible, sees use's Exit
)
```

Signature:

```ts
acquireUseRelease(
  acquire: Effect<A, E, R>,
  use: (a: A) => Effect<A2, E2, R2>,
  release: (a: A, exit: Exit<A2, E2>) => Effect<X, never, R3>
): Effect<A2, E | E2, R | R2 | R3>
```

The `release` callback receives the `Exit` of `use`, so you can branch (e.g. commit on `Exit.Success`, roll back otherwise). Use this when the resource's lifetime is exactly one use-block. Reach for `acquireRelease` + `scoped` when the resource must live across a wider region or be combined with others.

## `Effect.acquireReleaseInterruptible`

Same as `acquireRelease` but the **acquire** step is interruptible. The release callback here takes only the `exit` (not the resource), because acquisition may have been interrupted mid-flight:

```ts
acquireReleaseInterruptible(
  acquire: Effect<A, E, R>,
  release: (exit: Exit<unknown, unknown>) => Effect<X, never, R2>
): Effect<A, E, Scope | R | R2>
```

Use it when acquisition is long-running and you genuinely want to abandon it on interruption (and your release can clean up whatever partial state exists). Default to plain `acquireRelease` otherwise.

## `Effect.addFinalizer` — register cleanup imperatively

Adds a finalizer to the ambient scope without an associated acquire. The finalizer receives the scope's closing `Exit`:

```ts
import { Effect, Console } from "effect"

const program = Effect.gen(function* () {
  yield* Effect.addFinalizer((exit) =>
    Console.log(`finalizer ran, exit=${exit._tag}`)
  )
  return "result"
})

// Effect<string, never, Scope> — provide & close the scope:
Effect.runPromiseExit(Effect.scoped(program))
// Output:
// finalizer ran, exit=Success
// { _id: 'Exit', _tag: 'Success', value: 'result' }
```

Signature: `addFinalizer((exit: Exit<unknown, unknown>) => Effect<X, never, R>): Effect<void, never, Scope | R>`. Like release, finalizers are `never`-failing and run uninterruptibly.

## `ensuring`, `onError`, `onExit` — finalizers scoped to one effect

These attach cleanup directly to a single effect and do **not** require a `Scope`. They differ by when they fire and what they receive:

| Operator | Runs on | Receives |
| --- | --- | --- |
| `Effect.ensuring(fin)` | success, failure, interruption | nothing |
| `Effect.onError(cleanup)` | failure & interruption (not success) | `Cause<E>` |
| `Effect.onExit(cleanup)` | success, failure, interruption | `Exit<A, E>` |

```ts
import { Effect, Console, Exit } from "effect"

// always — good for "stop spinner", "release lock"
task.pipe(Effect.ensuring(Console.log("done (any outcome)")))

// only on failure/interruption — good for compensating actions
task.pipe(Effect.onError((cause) => Console.log(`failed: ${cause}`)))

// branch on the result
task.pipe(
  Effect.onExit((exit) =>
    Exit.isSuccess(exit)
      ? Console.log("committed")
      : Console.log("rolled back")
  )
)
declare const task: Effect.Effect<string, Error>
```

All three cleanups run **uninterruptibly**. `onError`/`ensuring`/`onExit` are the right tool for cleanup tied to a single effect; `addFinalizer` + `Scope` is right when the cleanup must live as long as the surrounding scope, alongside other resources.

❌ Don't reach for `onExit` when you have a real acquire/release pair — you lose the uninterruptible-acquire guarantee. ✅ Do use `acquireRelease`.

## `Effect.scoped` — provide & close a fresh scope

`Effect.scoped` is how you discharge a `Scope` requirement. It creates a new scope, runs the effect, and closes the scope (running all finalizers) when the effect completes — by success, failure, or interruption:

```ts
import { Effect } from "effect"

//      ┌─── Effect<A, E, R | Scope>
const scopedWork: Effect.Effect<string, never, Scope.Scope> = Effect.gen(function* () {
  const db = yield* conn          // adds finalizer
  return yield* db.query("...").pipe(Effect.as("ok"))
})

//      ┌─── Effect<string, never, never>  ← Scope discharged
//      ▼
const runnable = Effect.scoped(scopedWork)
```

Type: `scoped(effect: Effect<A, E, R>): Effect<A, E, Exclude<R, Scope>>`.

Related:
- `Effect.scopedWith(f)` / `Effect.scopeWith(f)` — run a function that gets the `Scope` directly.
- `Effect.scope` — `Effect<Scope, never, Scope>`, grabs the current scope (e.g. to pass to `forkIn`).

## Finalizer ordering: LIFO, and execution strategy

Finalizers run in **reverse order of registration** (last acquired, first released) — the natural nesting order for dependent resources:

```ts
import { Effect, Console } from "effect"

const program = Effect.gen(function* () {
  yield* Effect.addFinalizer(() => Console.log("close 1 (acquired first)"))
  yield* Effect.addFinalizer(() => Console.log("close 2"))
  yield* Effect.addFinalizer(() => Console.log("close 3 (acquired last)"))
})

Effect.runFork(Effect.scoped(program))
// Output:
// close 3 (acquired last)
// close 2
// close 1 (acquired first)
```

To run independent finalizers concurrently, switch the scope's execution strategy with `Effect.parallelFinalizers` (and `Effect.sequentialFinalizers` to switch back). Only do this when the cleanups are genuinely independent — concurrent finalizers can race.

## Manual scope: `Scope.make` / `extend` / `close`

You rarely need these, but when you must control a scope's lifetime explicitly (e.g. it outlives any single effect), use the `Scope` module directly:

```ts
import { Effect, Scope, Exit } from "effect"

const program = Effect.gen(function* () {
  // 1. Create a closeable scope (finalizers run sequentially by default)
  const scope = yield* Scope.make()

  // 2. Extend a scoped effect INTO this scope — provides the scope but does
  //    NOT close it when the effect finishes.
  yield* conn.pipe(Scope.extend(scope))

  // ... resource stays alive across as much work as you like ...

  // 3. Close explicitly — runs all finalizers with the given Exit.
  yield* Scope.close(scope, Exit.void)
})
```

- `Scope.make(strategy?)` → `Effect<CloseableScope>` — fresh scope, `sequential` finalizers unless told otherwise.
- `Scope.extend(effect, scope)` → provides `scope` to `effect`, leaves it open. Use to attach a resource to a longer-lived scope.
- `Scope.use(effect, scope)` → provides the closeable scope and closes it when `effect` completes. This is essentially what `Effect.scoped` does with a fresh scope.
- `Scope.close(scope, exit)` → runs finalizers. Only callable on a `CloseableScope`.
- `Scope.addFinalizer` / `Scope.addFinalizerExit` — register on a specific scope.

❌ Don't manually `Scope.make`/`close` for routine resource use — it's verbose and easy to leak (forget to `close`, or `close` before some `extend`). ✅ Do prefer `Effect.scoped` / `acquireRelease` / `Layer.scoped`.

## Scoped resources in layers: `Layer.scoped`

A layer's scope is tied to the **application's lifetime**, not to a single request. `Layer.scoped` builds a service from a scoped effect; its finalizers run when the app (the layer's enclosing scope) shuts down. This is how you wire connection pools, background workers, and clients that must close cleanly on exit.

```ts
import { Context, Effect, Layer } from "effect"

class Database extends Context.Tag("Database")<Database, DbConn>() {}

//      ┌─── Layer<Database, never, never>
//      ▼
const DatabaseLive = Layer.scoped(
  Database,
  Effect.acquireRelease(
    Effect.promise(() => openConn()),
    (db) => Effect.promise(() => db.close())
  )
)
```

Type: `Layer.scoped(tag, effect: Effect<S, E, R>): Layer<I, E, Exclude<R, Scope>>` — the `Scope` is absorbed into the layer's lifecycle.

When you build the app's runtime from this layer, the connection opens once at startup and the finalizer fires once at shutdown. Acquired-once / released-at-shutdown is the defining property of a `Layer.scoped` service — don't recreate the resource per use. Use `Layer.scopedDiscard` for a finalizer-only layer that provides no service.

## The bracket pattern, summarized

1. **Single use-block, known up front** → `Effect.acquireUseRelease(acquire, use, release)`.
2. **Resource lives across a region, possibly combined with others** → `Effect.acquireRelease(acquire, release)`, then run inside `Effect.scoped`.
3. **App-lifetime resource (pool, client, worker)** → `Layer.scoped`.
4. **Ad-hoc cleanup on a single effect** → `ensuring` / `onError` / `onExit`.
5. **Imperative finalizer in a scoped block** → `Effect.addFinalizer`.

All of them guarantee release on success, failure, and **interruption** — which is exactly why fibers can be torn down safely (see concurrency reference).

## See also

- [07-concurrency-fibers.md](07-concurrency-fibers.md) — interruption model, `forkScoped`/`forkIn` (fibers tied to a scope), and why interruption is safe precisely because finalizers always run.
- [Context, Services & Layers](05-context-layers.md) — `Layer.scoped`, building runtimes, and how the app scope ties to layer finalizers.
