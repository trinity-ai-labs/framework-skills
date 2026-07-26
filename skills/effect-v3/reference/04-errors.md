# Error Management

Reach for this section whenever you need to model, raise, catch, transform, or accumulate errors in Effect — and especially when you need to reason about the difference between expected failures and unexpected defects.

---

## Contents

- [The two error channels: `E` vs defects](#the-two-error-channels-e-vs-defects)
- [Defining domain errors](#defining-domain-errors)
- [Producing errors](#producing-errors)
- [Recovering from errors](#recovering-from-errors)
- [Inspecting and converting the error channel](#inspecting-and-converting-the-error-channel)
- [`Cause<E>` anatomy](#causee-anatomy)
- [`Exit<A, E>` — the final result of a fiber](#exita-e-the-final-result-of-a-fiber)
- [Error accumulation vs short-circuit](#error-accumulation-vs-short-circuit)
- [Cleanup that runs on error or interrupt](#cleanup-that-runs-on-error-or-interrupt)
- [A note on `retry`](#a-note-on-retry)
- [See also](#see-also)


## The two error channels: `E` vs defects

Every `Effect<A, E, R>` carries a **typed error channel `E`** and an implicit **defect channel**.

| Kind | Lives in | Caught by | Means |
|---|---|---|---|
| **Expected error** (`Fail`) | `E` | `catchAll`, `catchTag`, `orElse` … | A condition your domain knows about and can recover from |
| **Defect** (`Die`) | outside `E` — only in `Cause` | `catchAllDefect`, `catchAllCause`, `sandbox` | A bug, assertion failure, or truly unexpected crash |
| **Interruption** | outside `E` — only in `Cause` | `catchAllCause` | Fiber was cancelled by the runtime or another fiber |

**Why it matters:** Effect's type system makes the distinction load-bearing. If a function returns `Effect<A, NetworkError, R>` the caller knows exactly what can go wrong. A `Die` inside that effect doesn't widen the `E` type — it is invisible at the type level (intentionally: bugs shouldn't be part of a protocol).

```ts
// ❌ throw an exception — becomes a Die/defect, bypasses typed recovery
const bad = Effect.sync(() => { throw new Error("oops") })
// type: Effect<never, never, never>  — but it *will* die at runtime

// ✅ use Effect.fail — becomes a typed Fail, fully recoverable
const good = Effect.fail(new Error("oops"))
// type: Effect<never, Error, never>
```

---

## Defining domain errors

### `Data.TaggedError` — the idiomatic choice

Use when serialization / schema validation is **not** needed. The result is a class that:

- extends `Error` (so stack traces work)
- sets `_tag` automatically
- is directly `yield*`-able (it implements `YieldableError`)
- supports structural equality via Effect's `Equal`

```ts
import { Data, Effect } from "effect"

class HttpError extends Data.TaggedError("HttpError")<{
  readonly status: number
  readonly url: string
}> {}

class ParseError extends Data.TaggedError("ParseError")<{
  readonly raw: string
}> {}

// Instantiate
const err = new HttpError({ status: 404, url: "/api/users" })

// Yield directly in a generator
const program = Effect.gen(function* () {
  yield* new HttpError({ status: 503, url: "/api/data" })
  //        ↑ shorthand for yield* Effect.fail(new HttpError(...))
})
// type: Effect<never, HttpError, never>
```

> `_tag` is set as a prototype property — do **not** pass it in the constructor args.

### `Schema.TaggedError` — when you need (de)serialization

Use when the error must cross a wire boundary (RPC, serialization layer, `@effect/platform` HttpApiDeclarative errors).

```ts
import { Schema } from "effect"

class ApiError extends Schema.TaggedError<ApiError>()("ApiError", {
  status: Schema.Number,
  message: Schema.String
}) {
  get userMessage() {
    return `HTTP ${this.status}: ${this.message}`
  }
}
```

`Schema.TaggedError` generates a full Schema for the class, so instances can be encoded/decoded with `Schema.encode` / `Schema.decode`. `Data.TaggedError` does not.

### Why tagged errors enable `catchTag`

Effect's `catchTag` / `catchTags` look for the **`readonly _tag` discriminant** on the error object. Any object with `_tag` works — plain interfaces are fine for small scripts:

```ts
// ❌ plain Error — no _tag, cannot use catchTag
Effect.fail(new Error("oops"))

// ✅ Data.TaggedError — has _tag, works with catchTag
Effect.fail(new HttpError({ status: 500, url: "/" }))

// ✅ plain tagged interface — also works
Effect.fail({ _tag: "NotFound" as const, id: "abc" })
```

---

## Producing errors

```ts
import { Effect, Cause } from "effect"

// Fail with a typed error
Effect.fail(new HttpError({ status: 404, url: "/" }))
// Effect<never, HttpError, never>

// Fail lazily (evaluated on demand, useful when construction has side effects)
Effect.failSync(() => new HttpError({ status: 500, url: "/" }))

// Fail with a raw Cause (when you have a Cause in hand)
Effect.failCause(Cause.fail(new HttpError({ status: 500, url: "/" })))
Effect.failCauseSync(() => Cause.fail(new HttpError({ status: 500, url: "/" })))

// Die — becomes a defect, NOT in the typed E channel
Effect.die(new Error("impossible state"))          // any value
Effect.dieMessage("impossible state")             // wraps in RuntimeException
Effect.dieSync(() => new Error("lazy defect"))

// Promote a typed failure to a defect (erase the error type)
Effect.orDie(Effect.fail(new HttpError({ status: 500, url: "/" })))
// Effect<never, never, never>  — the error is now a defect

// Promote, mapping the error first
Effect.orDieWith(
  Effect.fail(new HttpError({ status: 500, url: "/" })),
  (e) => new Error(`Unexpected HTTP ${e.status} from ${e.url}`)
)
```

---

## Recovering from errors

### `catchAll` — recover from all typed failures

```ts
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const data = yield* fetchData().pipe(
    Effect.catchAll((err) =>
      Effect.succeed({ fallback: true, error: err })
    )
  )
  return data
})
// Error channel is now never
```

### `catchAllCause` — recover from everything (failures + defects + interrupts)

```ts
Effect.catchAllCause(program, (cause) =>
  Effect.succeed(`Recovered from cause: ${cause}`)
)
// Use sparingly — swallows defects too
```

### `catchAllDefect` — handle only defects

```ts
Effect.catchAllDefect(program, (defect) => {
  console.error("Unexpected defect:", defect)
  return Effect.succeed("degraded")
})
// Typed failures pass through unchanged
```

### `catchTag` — recover from one tagged error type

```ts
// Single tag
const recovered = program.pipe(
  Effect.catchTag("HttpError", (e) =>
    Effect.succeed(`fallback after HTTP ${e.status}`)
  )
)

// Multiple tags at once (variadic overload, v3.x)
const recovered2 = program.pipe(
  Effect.catchTag("HttpError", "ParseError", (e) =>
    // e is HttpError | ParseError
    Effect.succeed("fallback")
  )
)
```

### `catchTags` — recover from multiple tagged error types with separate handlers

```ts
// ✅ idiomatic multi-error handling
const recovered = program.pipe(
  Effect.catchTags({
    HttpError: (e) => Effect.succeed(`HTTP fallback: ${e.status}`),
    ParseError: (e) => Effect.logWarning(`Bad parse: ${e.raw}`).pipe(
      Effect.andThen(Effect.succeed("default"))
    )
  })
)
// Remaining error types stay in the E channel
```

### `catchIf` — recover based on a predicate (with type narrowing)

```ts
Effect.catchIf(
  program,
  (e): e is HttpError => e._tag === "HttpError" && e.status >= 500,
  (e) => Effect.succeed("retrying server error")
)
// If the predicate doesn't narrow, the full E type remains in the channel
```

### `catchSome` — optionally recover (return `Option.some(effect)` to recover, `Option.none()` to pass through)

```ts
import { Option } from "effect"

Effect.catchSome(program, (e) =>
  e._tag === "HttpError" && e.status === 503
    ? Option.some(Effect.succeed("service unavailable fallback"))
    : Option.none()
)
// E channel: unchanged (the type system keeps it because recovery is partial)
```

### `catchSomeCause` / `catchSomeDefect` — partial recovery over Cause / defects

```ts
import { Cause, Option } from "effect"

// Catch only IllegalArgumentException defects
Effect.catchSomeDefect(program, (defect) =>
  Cause.isIllegalArgumentException(defect)
    ? Option.some(Effect.succeed("bad input, recovered"))
    : Option.none()
)
```

### Fallback combinators

```ts
// Replace the entire failing effect with another
Effect.orElse(fetchPrimary, () => fetchFallback)

// Replace failure with a constant failure value (lazy)
Effect.orElseFail(program, () => new HttpError({ status: 503, url: "/" }))

// Replace failure with a constant success value (lazy)
Effect.orElseSucceed(program, () => defaultValue)

// Try each effect in sequence; return first success or last error
Effect.firstSuccessOf([tryNode1, tryNode2, tryNode3])
```

---

## Inspecting and converting the error channel

### `Effect.either` / `Effect.option` / `Effect.exit` — surface errors as values

```ts
import { Effect, Either, Option, Exit } from "effect"

// Wrap result in Either — Left = error, Right = success. Never fails.
const asEither: Effect<Either.Either<A, E>, never, R> = Effect.either(program)

// Wrap result in Option — None = error (loses the error), Some = success. Never fails.
const asOption: Effect<Option.Option<A>, never, R> = Effect.option(program)

// Wrap result in Exit — carries full Cause on failure. Never fails.
const asExit: Effect<Exit.Exit<A, E>, never, R> = Effect.exit(program)

// Flip success and failure channels
const flipped: Effect<E, A, R> = Effect.flip(program)
```

### `mapError` / `mapBoth` — transform without recovering

```ts
// Transform only the error type
const mapped = program.pipe(
  Effect.mapError((e) => new WrappedError({ cause: e, context: "fetchUser" }))
)

// Transform both success and error
const both = program.pipe(
  Effect.mapBoth({
    onFailure: (e) => new WrappedError({ cause: e, context: "ctx" }),
    onSuccess: (a) => ({ value: a, cached: false })
  })
)
```

### `tapError` / `tapErrorTag` / `tapErrorCause` / `tapDefect` — side effects without recovery

```ts
// Side-effect on any failure (does not modify the error channel)
program.pipe(
  Effect.tapError((e) => Effect.logError(`Error: ${e._tag}`))
)

// Side-effect only on a specific tag
program.pipe(
  Effect.tapErrorTag("HttpError", (e) =>
    Effect.logWarning(`HTTP ${e.status} at ${e.url}`)
  )
)

// Side-effect on the full Cause (includes defects)
program.pipe(
  Effect.tapErrorCause((cause) =>
    Effect.logError(`Full cause: ${cause}`)
  )
)

// Side-effect only on defects
program.pipe(
  Effect.tapDefect((cause) =>
    Effect.logCritical(`Defect! ${cause}`)
  )
)
```

### `Effect.cause` — extract the `Cause` as a value

```ts
// Returns the Cause of failure without failing; succeeds with Cause.empty on success
const cause: Effect<Cause.Cause<E>, never, R> = Effect.cause(program)
```

### `ignore` / `ignoreLogged` — discard result and error

```ts
// Discards everything — success AND typed failures. Defects still propagate.
Effect.ignore(program)         // Effect<void, never, R>

// Same but logs failures at the Warning level before discarding
Effect.ignoreLogged(program)   // Effect<void, never, R>
```

---

## `Cause<E>` anatomy

`Cause<E>` is Effect's model for **why** a fiber stopped. It can be composed from:

| Variant | Constructor | Meaning |
|---|---|---|
| `Empty` | `Cause.empty` | No failure (rare, base case) |
| `Fail<E>` | `Cause.fail(e)` | Expected typed failure |
| `Die` | `Cause.die(defect)` | Unexpected/unrecoverable defect |
| `Interrupt` | `Cause.interrupt(fiberId)` | Fiber cancelled |
| `Sequential<E>` | `Cause.sequential(left, right)` | Two causes happened in sequence |
| `Parallel<E>` | `Cause.parallel(left, right)` | Two causes happened in parallel |

```ts
import { Cause } from "effect"

// Inspect a cause
Cause.isFailure(cause)     // has at least one Fail
Cause.isDie(cause)         // has at least one Die
Cause.isInterrupted(cause) // has at least one Interrupt

Cause.failures(cause)      // Chunk of all E values
Cause.defects(cause)       // Chunk of all defect values
Cause.interruptors(cause)  // HashSet of fiber IDs

// Match over a cause
Cause.match(cause, {
  onEmpty: ...,
  onFail: (e) => ...,
  onDie: (defect) => ...,
  onInterrupt: (fiberId) => ...,
  onSequential: (left, right) => ...,
  onParallel: (left, right) => ...
})

// Squash to a single unknown (for rethrowing or logging)
Cause.squash(cause)        // unknown
```

### `sandbox` / `unsandbox` — expose or hide the full `Cause`

```ts
// Lift the Cause into the error channel so typed operators can work on it
const sandboxed: Effect<A, Cause.Cause<E>, R> = Effect.sandbox(program)

// Use catchTags/catchAll on the Cause
const handled = sandboxed.pipe(
  Effect.catchTags({
    Die: (cause) => Effect.succeed("recovered from defect"),
    Interrupt: (cause) => Effect.succeed("recovered from interrupt")
  })
)

// Restore the original E type
const restored: Effect<A, E, R> = Effect.unsandbox(handled)
```

`sandbox` is the escape hatch when you need to handle defects or interrupts with typed operators that normally only see `E`.

---

## `Exit<A, E>` — the final result of a fiber

```ts
import { Exit, Cause } from "effect"

// Constructors
Exit.succeed(42)                          // Exit<number, never>
Exit.fail(new HttpError({ ... }))         // Exit<never, HttpError>
Exit.failCause(Cause.die(new Error()))    // Exit<never, never>  (defect exit)
Exit.die(new Error("boom"))              // Exit<never, never>
Exit.interrupt(fiberId)                   // Exit<never, never>

// Inspection
Exit.isSuccess(exit)  // boolean
Exit.isFailure(exit)  // boolean

// Pattern match
Exit.match(exit, {
  onSuccess: (value) => `succeeded with ${value}`,
  onFailure: (cause) => `failed with ${Cause.pretty(cause)}`
})

// Async pattern match (returns Effect)
Exit.matchEffect(exit, {
  onSuccess: (value) => Effect.succeed(value),
  onFailure: (cause) => Effect.logError(`cause: ${cause}`).pipe(Effect.andThen(Effect.fail(cause)))
})

// Retrieve value or compute fallback from Cause
Exit.getOrElse(exit, (cause) => defaultValue)
```

---

## Error accumulation vs short-circuit

By default `Effect.all` short-circuits on the first failure. Use these to collect all results:

### `Effect.all` with `mode`

```ts
import { Effect, Either, Option } from "effect"

const effects = [task1, task2, task3]

// mode: "either" — runs all, collects Either[]
const asEithers = Effect.all(effects, { mode: "either" })
// Effect<Either<A, E>[], never, R>  — never fails

// mode: "validate" — runs all, fails with Option<E>[] (None=ok, Some=err)
const validated = Effect.all(effects, { mode: "validate" })
// Effect<A[], Option<E>[], R>  — fails if any fail
```

### `Effect.validateAll` — apply f to iterable, accumulate ALL failures

```ts
import { Effect } from "effect"

// Runs all, collects successes into array; fails with array of ALL errors
const result = Effect.validateAll(
  [1, 2, 3, 4, 5],
  (n) => n % 2 === 0 ? Effect.succeed(n) : Effect.fail(`${n} is odd`)
)
// On partial failure: Effect<never, string[], never>
// On total success:   Effect<number[], never, never>

// Concurrent version
const concurrent = Effect.validateAll(inputs, validate, { concurrency: "unbounded" })

// Discard successes — only care about the error array
const errorsOnly = Effect.validateAll(inputs, validate, { discard: true })
```

### `Effect.validateFirst` — stop at first success, accumulate failures until then

```ts
// Like validateAll but short-circuits on the FIRST success (opposite of the default)
const result = Effect.validateFirst(
  [1, 3, 5, 6, 7],
  (n) => n % 2 === 0 ? Effect.succeed(n) : Effect.fail(n)
)
// Succeeds with 6; fails with [1, 3, 5, 6, 7] if none succeed
```

### `Effect.partition` — split an iterable into `[errors, successes]`

```ts
// Never fails. Always returns [failures, successes].
const [errors, results] = yield* Effect.partition(
  [0, 1, 2, 3, 4],
  (n) => n % 2 === 0 ? Effect.succeed(n) : Effect.fail(`${n} is odd`)
)
// errors:  ["1 is odd", "3 is odd"]
// results: [0, 2, 4]

// Concurrent
const [errors2, results2] = yield* Effect.partition(inputs, validate, {
  concurrency: "unbounded"
})
```

---

## Cleanup that runs on error or interrupt

These run their finalizer **uninterruptibly** — the cleanup always completes.

```ts
// Runs regardless of success, failure, or interruption
Effect.ensuring(program, cleanup)
// cleanup: Effect<any, never, R2>  — cannot fail itself

// Runs ONLY on failure or interruption; receives the Cause
Effect.onError(program, (cause) =>
  Effect.logError(`Failed: ${Cause.pretty(cause)}`)
)

// Runs on ALL exits (success/failure/interrupt); receives the Exit
Effect.onExit(program, (exit) =>
  Exit.match(exit, {
    onSuccess: (v) => Effect.log(`Done: ${v}`),
    onFailure: (cause) => Effect.logError(`Cause: ${cause}`)
  })
)
```

For resource lifecycle (acquire → use → release), use `acquireRelease` / `acquireUseRelease` — see [Resources & Scope](06-resources-scope.md).

---

## A note on `retry`

`Effect.retry` accepts either a `Schedule` or an options object and re-runs the effect when it fails with a typed error:

```ts
import { Effect, Schedule } from "effect"

// Retry up to 3 times with exponential backoff.
// `intersect` = continue only while BOTH schedules want to → recurs(3) caps it.
const retried = program.pipe(
  Effect.retry(Schedule.exponential("100 millis").pipe(Schedule.intersect(Schedule.recurs(3))))
)

// Retry with options object (filter by error tag)
const retried2 = program.pipe(
  Effect.retry({ times: 5, while: (e) => e._tag === "HttpError" })
)
```

Retry does **not** catch defects — only typed `E` failures. For full scheduling depth, see [Scheduling & time](09-scheduling-time.md).

---

## See also

- [Context, Services & Layers](05-context-layers.md)
- [Resources & Scope](06-resources-scope.md)
- [Concurrency & Fibers](07-concurrency-fibers.md)
- [Scheduling & time](09-scheduling-time.md)
- [Schema & Config](11-schema.md) — for `Schema.TaggedError` serialization
