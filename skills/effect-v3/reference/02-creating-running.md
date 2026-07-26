# Creating and Running Effects

## Contents

- [Constructors](#constructors)
- [Running Effects (the Program Edge)](#running-effects-the-program-edge)
- [`ManagedRuntime` — Long-Lived Apps](#managedruntime-long-lived-apps)
- [The Core Principle](#the-core-principle)
- [See also](#see-also)

---


Build effect descriptions everywhere; run only at the program edge.

## Constructors

### `Effect.succeed` — wrap a known value

```ts
import { Effect } from "effect"

//      ┌─── Effect<number, never, never>
//      ▼
const n = Effect.succeed(42)
```

### `Effect.fail` — typed recoverable failure

```ts
import { Effect } from "effect"

class NotFound { readonly _tag = "NotFound" }

//      ┌─── Effect<never, NotFound, never>
//      ▼
const err = Effect.fail(new NotFound())
```

### `Effect.sync` — synchronous side effect that will not throw

```ts
import { Effect } from "effect"

const now = Effect.sync(() => Date.now())
//    ┌─── Effect<number, never, never>
```

If the thunk throws, the throw becomes a **defect** (`die`), not a typed error. Use `Effect.try` when the thunk may throw.

### `Effect.try` — synchronous computation that may throw

```ts
import { Effect } from "effect"

// Without catch — error becomes UnknownException
const parse1 = Effect.try(() => JSON.parse(rawJson))
// Effect<any, Cause.UnknownException, never>

// With catch — map the thrown value to your error type
const parse2 = Effect.try({
  try: () => JSON.parse(rawJson),
  catch: (e) => new SyntaxError(`Invalid JSON: ${e}`)
})
// Effect<any, SyntaxError, never>
```

### `Effect.promise` — async that will not reject

```ts
import { Effect } from "effect"

// The AbortSignal is wired to fiber interruption automatically
const delay = (ms: number) =>
  Effect.promise<void>(
    (signal) => new Promise((resolve) => setTimeout(resolve, ms))
  )
// Effect<void, never, never>
```

If the promise rejects, it becomes a **defect**. Use `Effect.tryPromise` when rejection is expected.

### `Effect.tryPromise` — async that may reject

```ts
import { Effect } from "effect"

// Without catch — rejection becomes UnknownException
const fetchRaw = (url: string) =>
  Effect.tryPromise((signal) => fetch(url, { signal }).then((r) => r.json()))
// Effect<any, Cause.UnknownException, never>

// With catch — map rejection to your error type
class FetchError { readonly _tag = "FetchError"; constructor(readonly cause: unknown) {} }

const fetchJson = (url: string) =>
  Effect.tryPromise({
    try: (signal) => fetch(url, { signal }).then((r) => r.json()),
    catch: (e) => new FetchError(e)
  })
// Effect<any, FetchError, never>
```

### `Effect.async` — wrapping callback-based APIs

```ts
import { Effect } from "effect"
import { readFile } from "node:fs"

const readFileEffect = (path: string) =>
  Effect.async<Buffer, NodeJS.ErrnoException>((resume, signal) => {
    const controller = new AbortController()
    signal.addEventListener("abort", () => controller.abort())
    readFile(path, (err, data) => {
      if (err) resume(Effect.fail(err))
      else resume(Effect.succeed(data))
    })
  })
```

The callback receives a `resume` function. Call it with `Effect.succeed(value)` or `Effect.fail(err)`. The optional second argument is an `AbortSignal` for cleanup; you can also return an `Effect<void>` cleanup from the register function.

### `Effect.suspend` — deferred construction (for recursion or cyclic deps)

```ts
import { Effect } from "effect"

// Without suspend, the recursive reference would be undefined at definition time
const countdown = (n: number): Effect.Effect<void> =>
  n <= 0
    ? Effect.void
    : Effect.suspend(() =>
        Effect.flatMap(
          Effect.log(`${n}`),
          () => countdown(n - 1)
        )
      )
```

Also use `suspend` to break reference cycles between modules.

### `Effect.fromNullable` — lift a nullable value

```ts
import { Effect } from "effect"

//      ┌─── Effect<string, Cause.NoSuchElementException, never>
//      ▼
const name = Effect.fromNullable(maybeString)
```

Returns a `NoSuchElementException` failure when the value is `null` or `undefined`.

### `Effect.void` — unit effect

```ts
import { Effect } from "effect"

// Effect<void, never, never>
const unit = Effect.void
```

### `Effect.die` — unrecoverable defect

```ts
import { Effect } from "effect"

const divide = (a: number, b: number) =>
  b === 0
    ? Effect.die(new Error("Division by zero"))
    : Effect.succeed(a / b)
// Effect<number, never, never> — programmer error, not a domain error
```

Use `die` / `dieMessage` for invariant violations that should never be recovered from.

---

## Running Effects (the Program Edge)

Run functions are **impure** — call them only at the outermost boundary of your program (e.g., `main`, a framework adapter, a test runner). Never call `runSync` / `runPromise` inside an `Effect` computation.

### Decision tree

| Need | Use |
|------|-----|
| Sync-only effect, result needed now | `Effect.runSync` |
| Sync-only, want Exit not throw | `Effect.runSyncExit` |
| Async, await the result | `Effect.runPromise` |
| Async, want Exit not rejection | `Effect.runPromiseExit` |
| Fire-and-forget, need the fiber handle | `Effect.runFork` |
| Callback / CPS interop | `Effect.runCallback` |
| Long-running app with many effects | `ManagedRuntime` |

### `Effect.runSync`

```ts
import { Effect } from "effect"

const result = Effect.runSync(Effect.succeed(42))
// => 42

// ❌ Throws if the effect has async boundaries or typed failures
// Effect.runSync(Effect.promise(() => Promise.resolve(1)))
// → throws AsyncFiberException
```

### `Effect.runSyncExit`

```ts
import { Effect, Exit } from "effect"

const exit = Effect.runSyncExit(Effect.fail("oops"))
// Exit.Exit<never, string>

if (Exit.isFailure(exit)) {
  console.error(exit.cause)
}
```

Returns an `Exit` (success or failure) rather than throwing. Async boundaries still produce a `Die` cause.

### `Effect.runPromise`

```ts
import { Effect } from "effect"

// Resolves with A on success; rejects with FiberFailure on failure
await Effect.runPromise(Effect.succeed("hello"))
// => "hello"

await Effect.runPromise(Effect.fail("boom")).catch(console.error)
// => logs: (FiberFailure) Error: boom

// Optional AbortSignal for cancellation
const controller = new AbortController()
await Effect.runPromise(longRunning, { signal: controller.signal })
```

### `Effect.runPromiseExit`

```ts
import { Effect, Exit } from "effect"

const exit = await Effect.runPromiseExit(Effect.fail("boom"))
// Exit.Exit<never, string> — never rejects

if (Exit.isSuccess(exit)) {
  console.log(exit.value)
} else {
  console.log(exit.cause) // Cause<string>
}
```

Always resolves (never rejects). Prefer this over `runPromise` when you need to inspect failure details without wrapping in try/catch.

### `Effect.runFork`

```ts
import { Effect, Fiber } from "effect"

// Returns a RuntimeFiber immediately — effect runs in the background
const fiber = Effect.runFork(
  Effect.gen(function* () {
    yield* Effect.sleep("1 second")
    return "done"
  })
)

// Join to await the result
const result = await Effect.runPromise(Fiber.join(fiber))
```

Use `runFork` when you need concurrent execution control (join, interrupt, race).

### `Effect.runCallback`

```ts
import { Effect, Exit, Runtime } from "effect"

// Returns a Cancel function
const cancel = Effect.runCallback(
  Effect.succeed(42),
  {
    onExit: (exit) => {
      if (Exit.isSuccess(exit)) console.log(exit.value)
      else console.error(exit.cause)
    }
  }
)

// Optionally cancel before completion:
// cancel()
```

---

## `ManagedRuntime` — Long-Lived Apps

When you have many effects to run against the same service layer (a server, a React app, a long-running CLI), build a `ManagedRuntime` once and reuse it.

```ts
import { Console, Effect, Layer, ManagedRuntime } from "effect"

// 1. Define a service
class Notifications extends Effect.Tag("Notifications")<
  Notifications,
  { readonly notify: (message: string) => Effect.Effect<void> }
>() {
  static Live = Layer.succeed(this, {
    notify: (message) => Console.log(`[notify] ${message}`)
  })
}

// 2. Build a ManagedRuntime from a Layer
const runtime = ManagedRuntime.make(Notifications.Live)

// 3. Run many effects against it — the Layer is built only once (memoized)
await runtime.runPromise(Notifications.notify("App started"))
await runtime.runPromise(Notifications.notify("Processing..."))

// 4. Dispose when done — finalizers and resources are released
await runtime.dispose()
```

`ManagedRuntime` exposes the same run methods as the module-level runners, but scoped to its layer:

```ts
// ManagedRuntime<R, ER> exposes:
runtime.runSync(effect)            // Effect<A, E, R> => A
runtime.runSyncExit(effect)        // Effect<A, E, R> => Exit<A, ER | E>
runtime.runPromise(effect)         // Effect<A, E, R> => Promise<A>
runtime.runPromiseExit(effect)     // Effect<A, E, R> => Promise<Exit<A, ER | E>>
runtime.runFork(effect)            // Effect<A, E, R> => RuntimeFiber<A, E | ER>
runtime.runCallback(effect, opts)  // => Cancel<A, E | ER>
await runtime.dispose()            // releases all resources
```

### Sharing a MemoMap across runtimes

```ts
import { Layer, ManagedRuntime } from "effect"

// runtimeB reuses already-built layers from runtimeA
const runtimeA = ManagedRuntime.make(myLayer)
const runtimeB = ManagedRuntime.make(myLayer, runtimeA.memoMap)
// myLayer is built only once
```

### Using ManagedRuntime as an Effect

`ManagedRuntime<R, ER>` is itself an `Effect<Runtime<R>, ER>`. You can `yield*` it inside a generator to get the underlying `Runtime<R>`:

```ts
import { Effect, Layer, ManagedRuntime } from "effect"

const managed = ManagedRuntime.make(myLayer)

const program = Effect.gen(function* () {
  const runtime = yield* managed          // Runtime<R>
  const ctx = runtime.context             // Context<R>
  // ...
})
```

### Common pattern: framework adapter (e.g., Next.js API route)

```ts
import { Layer, ManagedRuntime } from "effect"

// Created once at module level (survives across requests in a warm instance)
const runtime = ManagedRuntime.make(AppLayer)

export async function GET(req: Request) {
  return runtime.runPromise(handleRequest(req))
}
```

---

## The Core Principle

```
┌──────────────────────────────────────────────────────┐
│  Build with Effect.gen / combinators everywhere      │
│  ─────────────────────────────────────────────────── │
│  Run (runSync / runPromise / runFork) only at the    │
│  outermost boundary of your program                  │
└──────────────────────────────────────────────────────┘
```

Never call `runSync` or `runPromise` inside an `Effect`. Compose instead.

## See also

- [01-mental-model.md](01-mental-model.md) — the three-channel type and Effect as lazy description
- [03-combinators.md](03-combinators.md) — `map`, `flatMap`, `all`, `forEach`, and control flow
