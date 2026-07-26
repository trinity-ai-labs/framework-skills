# Effect Testing with `@effect/vitest`

When you reach for this: you need to write unit or integration tests for Effect code with Vitest, control time deterministically, swap services for fakes, or run property-based tests.

---

## Contents

- [Setup](#setup)
- [Test runners](#test-runners)
- [Assertion style](#assertion-style)
- [`.each`, `.skip`, `.only`, `.fails`](#each-skip-only-fails)
- [`TestClock` — deterministic time](#testclock-deterministic-time)
- [Sharing a Layer across tests](#sharing-a-layer-across-tests)
- [Swapping a service for a fake](#swapping-a-service-for-a-fake)
- [Asserting a typed failure](#asserting-a-typed-failure)
- [Property-based testing](#property-based-testing)
- [`TestContext`](#testcontext)
- [Common pitfalls](#common-pitfalls)
- [See also](#see-also)


## Setup

```sh
pnpm add -D vitest @effect/vitest
```

Import from `@effect/vitest` — it re-exports everything from `vitest` plus Effect-aware test runners:

```ts
import { it, describe, expect, layer } from "@effect/vitest"
import { assert } from "@effect/vitest/utils"  // for deepStrictEqual, strictEqual, assertTrue, etc.
```

`@effect/vitest` re-exports the full vitest API (`describe`, `beforeEach`, `afterAll`, etc.), so a single import covers both.

---

## Test runners

| Runner | What it provides | When to use |
|---|---|---|
| `it.effect` | `TestContext` (TestClock, TestRandom, …) auto-injected | Default — most unit tests |
| `it.scoped` | `TestContext` + a managed `Scope` | Tests that `acquireRelease` resources |
| `it.live` | Real (live) environment — no test services | Tests that need actual time / real I/O |
| `it.scopedLive` | Live environment + Scope | Live resources that need cleanup |
| `it.flakyTest` | Retry wrapper until pass or timeout | Non-deterministic tests |

### `it.effect`

```ts
import { it, expect } from "@effect/vitest"
import { Effect } from "effect"

it.effect("divides correctly", () =>
  Effect.gen(function* () {
    const result = yield* divide(10, 2)   // your Effect
    expect(result).toBe(5)
  })
)
```

The third argument is an optional timeout in ms (default 5000):

```ts
it.effect("slow operation", () => myEffect, 15_000)
```

### `it.scoped`

Use when the effect returns a resource via `acquireRelease`. The scope is finalised after the test body completes:

```ts
import { it } from "@effect/vitest"
import { Console, Effect } from "effect"

const acquire = Console.log("acquire")
const release = Console.log("release")
const resource = Effect.acquireRelease(acquire, () => release)

it.scoped("manages resource lifecycle", () =>
  Effect.gen(function* () {
    yield* resource        // resource is acquired; released when test ends
  })
)
```

❌ Don't use `it.effect` when your effect requires a `Scope` — TypeScript will flag it.

✅ Use `it.scoped` for any effect that internally calls `Effect.acquireRelease`.

### `it.live`

Runs in the real environment. Use when you actually need system time, real timers, or real I/O:

```ts
import { it } from "@effect/vitest"
import { Clock, Effect } from "effect"

it.live("uses real clock", () =>
  Effect.gen(function* () {
    const ms = yield* Clock.currentTimeMillis
    // ms is the real wall-clock time
  })
)
```

Note: `it.effect` suppresses log output by default; `it.live` does not.

### `it.flakyTest`

Wraps an Effect that sometimes fails, retrying until it succeeds or the timeout elapses:

```ts
import { it } from "@effect/vitest"
import { Effect, Random } from "effect"

const flaky = Effect.gen(function* () {
  const ok = yield* Random.nextBoolean
  if (!ok) yield* Effect.fail("bad luck")
})

it.effect("retries flaky test", () =>
  it.flakyTest(flaky, "5 seconds")
)
```

---

## Assertion style

Effect's own test suite uses `assert` from `@effect/vitest/utils` (Chai-style, works well with `Effect.gen`). Both `assert` and `expect` are available:

```ts
import { it } from "@effect/vitest"
import { deepStrictEqual, strictEqual, assertTrue, assertFalse } from "@effect/vitest/utils"
import { Effect } from "effect"

it.effect("counter increments", () =>
  Effect.gen(function* () {
    const result = yield* myCounter
    strictEqual(result, 3)
    deepStrictEqual(result, 3)
    assertTrue(result > 0)
  })
)
```

Use `expect` from `@effect/vitest` when you prefer Vitest's matcher style (`.toBe`, `.toEqual`, `.toStrictEqual`). Both are valid.

---

## `.each`, `.skip`, `.only`, `.fails`

Standard Vitest modifiers all work:

```ts
it.effect.each([1, 2, 3])("squares %s", (n) =>
  Effect.sync(() => expect(n * n).toBeGreaterThan(0))
)

it.effect.skip("not ready yet", () => Effect.void)
it.effect.only("focus on this", () => Effect.void)
it.effect.fails("known broken", () => Effect.fail("oops"))
it.effect.skipIf(process.env.CI === "true")("skip on CI", () => Effect.void)
it.effect.runIf(process.env.NODE_ENV === "test")("only in test env", () => Effect.void)
```

---

## `TestClock` — deterministic time

`it.effect` automatically provides `TestClock`. The test clock starts at time `0` and does **not** advance on its own — you control it:

```ts
import { it } from "@effect/vitest"
import { Effect, TestClock } from "effect"

it.effect("advances time by 1 second", () =>
  Effect.gen(function* () {
    yield* TestClock.adjust("1000 millis")
    // or: yield* TestClock.adjust(1000)      // numbers are milliseconds

    // Now the clock reads 1000 ms
    yield* TestClock.setTime(new Date("2025-01-01"))   // absolute time
  })
)
```

### Worked example: testing a Schedule-based retry without real waiting

```ts
import { it, expect } from "@effect/vitest"
import { Effect, Fiber, Ref, Schedule, TestClock } from "effect"

it.effect("retries 3 times with exponential backoff — no real waiting", () =>
  Effect.gen(function* () {
    const attempts = yield* Ref.make(0)

    // An effect that fails until the 3rd attempt
    const program = Effect.gen(function* () {
      const n = yield* Ref.updateAndGet(attempts, (x) => x + 1)
      if (n < 3) return yield* Effect.fail("not yet")
      return "success"
    }).pipe(
      Effect.retry(
        Schedule.recurs(5).pipe(
          Schedule.addDelay(() => "1 seconds")
        )
      )
    )

    // Fork so TestClock.adjust can unblock the sleeping fibers
    const fiber = yield* Effect.fork(program)

    // Let the first attempt run, fail, and park waiting for 1s
    yield* Effect.yieldNow()

    // Advance clock 1s → triggers retry #2
    yield* TestClock.adjust("1 seconds")
    yield* Effect.yieldNow()

    // Advance clock 1s → triggers retry #3 (succeeds)
    yield* TestClock.adjust("1 seconds")

    const result = yield* Fiber.join(fiber)
    expect(result).toBe("success")

    const count = yield* Ref.get(attempts)
    expect(count).toBe(3)
  })
)
```

`TestClock.adjust` unblocks any fibers that are sleeping via `Effect.sleep` or `Schedule` delays — the key pattern is **fork → yieldNow → adjust** to step through time-based logic without real waiting.

---

## Sharing a Layer across tests

Use the `layer(SomeLayer)(...)` block exported from `@effect/vitest`. The layer is built once per `describe` block and shared across all `it.effect` tests inside it:

```ts
import { expect, layer } from "@effect/vitest"
import { Context, Effect, Layer } from "effect"

class Database extends Context.Tag("Database")<Database, { query: (sql: string) => Effect.Effect<unknown[]> }>() {
  static Live = Layer.succeed(Database, {
    query: (sql) => Effect.succeed([])
  })
}

class Cache extends Context.Tag("Cache")<Cache, { get: (k: string) => Effect.Effect<string | null> }>() {
  static Live = Layer.effect(
    Cache,
    Effect.map(Database, (db) => ({ get: (k) => Effect.succeed(null) }))
  )
}

// Layer.Live is constructed once, shared by all tests in this block
layer(Database.Live)("Database layer", (it) => {
  it.effect("can query", () =>
    Effect.gen(function* () {
      const db = yield* Database
      const rows = yield* db.query("SELECT 1")
      expect(rows).toEqual([])
    })
  )

  // Nested layer: Database.Live is already in scope, add Cache.Live on top
  it.layer(Cache.Live)("with Cache", (it) => {
    it.effect("has both services", () =>
      Effect.gen(function* () {
        const db    = yield* Database
        const cache = yield* Cache
        const val   = yield* cache.get("key")
        expect(val).toBeNull()
      })
    )
  })
})
```

`layer()` accepts a `Layer` and optional `{ memoMap, timeout, excludeTestServices }`. When `excludeTestServices` is `false` (default), the layer is composed with `TestContext` so the inner tests still have `TestClock` etc.

**The usual real-world shape** is a suite-wide layer built from the service under test with its dependency faked — the two techniques stack:

```ts
// UserRepo declares `dependencies: [Database.Default]`, so use the raw layer or
// the stub won't land (see the warning under the next section).
const UserRepoTest = UserRepo.DefaultWithoutDependencies.pipe(
  Layer.provide(Layer.succeed(Database, Database.make({ query: () => Effect.succeed([]) })))
)

layer(UserRepoTest)("UserRepo", (it) => {
  it.effect("finds nothing in an empty table", () =>
    Effect.gen(function* () {
      const repo = yield* UserRepo
      // …one construction of UserRepo + the stub, shared by every test here
    })
  )
})
```

---

## Swapping a service for a fake

Inject a test double per-test with `Effect.provide`:

```ts
import { it, expect } from "@effect/vitest"
import { Context, Effect, Layer } from "effect"

class Mailer extends Context.Tag("Mailer")<Mailer, { send: (to: string, msg: string) => Effect.Effect<void> }>() {}

// No `dependencies` here on purpose: that leaves `Mailer` in `UserService.Default`'s
// RIn, which is what lets the fake below actually land. See the warning under the code.
class UserService extends Effect.Service<UserService>()("UserService", {
  effect: Effect.gen(function* () {
    const mailer = yield* Mailer
    return {
      invite: (email: string) => mailer.send(email, "Welcome!")
    }
  })
}) {}

it.effect("invite sends an email", () =>
  Effect.gen(function* () {
    const sent: string[] = []

    const FakeMailer = Layer.succeed(Mailer, {
      send: (to) => Effect.sync(() => { sent.push(to) })
    })

    const svc = yield* UserService.pipe(
      Effect.provide(UserService.Default.pipe(Layer.provide(FakeMailer)))
    )

    yield* svc.invite("alice@example.com")
    expect(sent).toEqual(["alice@example.com"])
  })
)
```

> **If the service declares `dependencies`, provide into `.DefaultWithoutDependencies` instead.** `Service.Default` has its declared dependency layers already provided, so `Service.Default.pipe(Layer.provide(Fake))` type-checks, runs, and quietly keeps the real implementation — the fake is built and ignored. Use `Service.DefaultWithoutDependencies.pipe(Layer.provide(Fake))`, or declare no `dependencies` (as above) and wire the graph at the provide site. Details in [`05-context-layers.md`](05-context-layers.md).

For test isolation patterns, see [`05-context-layers.md`](05-context-layers.md).

---

## Asserting a typed failure

`it.effect` fails the test when the effect fails, so don't let the error escape — move it into the success channel and assert on it as a value.

```ts
import { it, expect } from "@effect/vitest"
import { Data, Effect, Exit, Cause } from "effect"

class UserNotFound extends Data.TaggedError("UserNotFound")<{ id: string }> {}

// `Effect.flip` — swaps the channels: the error becomes the success value.
// Best when you expect a failure and want to assert on its fields.
it.effect("findById fails with UserNotFound", () =>
  Effect.gen(function* () {
    const error = yield* Effect.flip(repo.findById("missing"))
    expect(error._tag).toBe("UserNotFound")
    expect(error.id).toBe("missing")
  })
)

// `Effect.exit` — keeps success and failure distinguishable, so the test still
// fails loudly (rather than throwing "flip on a success") if the effect succeeds.
it.effect("findById fails, checked via Exit", () =>
  Effect.gen(function* () {
    const exit = yield* Effect.exit(repo.findById("missing"))
    expect(Exit.isFailure(exit)).toBe(true)
    if (Exit.isFailure(exit)) {
      const failure = Cause.failureOption(exit.cause)
      expect(failure._tag === "Some" && failure.value._tag).toBe("UserNotFound")
    }
  })
)
```

Reach for `Effect.either` when the assertion reads better as `Either.isLeft`. All three are documented in [`04-errors.md`](04-errors.md) — but note a defect (`Effect.die`, a thrown exception) is *not* caught by `flip`/`either`; only `Effect.exit` surfaces it, in the `Cause`.

---

## Property-based testing

`it.prop` integrates `fast-check` via `Effect.FastCheck` and `Arbitrary.make` for `Schema`-derived arbitraries:

```ts
import { it } from "@effect/vitest"
import { FastCheck, Schema } from "effect"

const FiniteNumber = Schema.Finite.pipe(Schema.nonNaN())

// Array form — each element is either a Schema (→ Arbitrary.make) or a raw fast-check Arbitrary
it.prop("addition is commutative", [FiniteNumber, FastCheck.integer()], ([a, b]) =>
  a + b === b + a
)

// Object form
it.prop("string includes itself", { a: Schema.String, b: Schema.String }, ({ a, b }) =>
  (a + b).includes(b)
)

// Effect-returning body
it.effect.prop("sums are commutative", [FiniteNumber, FastCheck.integer()], ([a, b]) =>
  Effect.gen(function* () {
    yield* Effect.void        // can yield effects
    return a + b === b + a    // return boolean to signal pass/fail
  })
)

// Pass fast-check options
it.prop("runs many cases", [Schema.String], ([s]) => s === s, {
  fastCheck: { numRuns: 1000 }
})
```

`Schema.Arbitrary` (accessible via `import { Arbitrary } from "effect"`) can also generate standalone `fast-check` arbitraries for use outside the test runner:

```ts
import { Arbitrary, Schema } from "effect"
import * as fc from "effect/FastCheck"

const arb = Arbitrary.make(Schema.Struct({ id: Schema.Number, name: Schema.String }))
fc.assert(fc.property(arb, (val) => typeof val.id === "number"))
```

---

## `TestContext`

`TestContext` is the layer that provides all test services:

```ts
import { TestContext } from "effect"
// TestContext.TestContext: Layer<TestServices>
// TestContext.live: Layer<TestServices, never, DefaultServices>
```

You rarely need to provide it manually because `it.effect` does so automatically. Use `TestContext.TestContext` explicitly only when running `Effect.runPromise` / `Effect.runFork` directly inside tests:

```ts
import { Effect, TestClock, TestContext } from "effect"

const testable = myEffect.pipe(Effect.provide(TestContext.TestContext))
```

---

## Common pitfalls

❌ Don't use `it.effect` for effects that use `acquireRelease` without a `Scope` — you'll get a type error about missing `Scope` in the requirements.

✅ Use `it.scoped`.

❌ Don't call `await Effect.runPromise(...)` inside `it.effect` — the outer runner already handles execution.

✅ Yield effects with `yield*` inside `Effect.gen`.

❌ Don't expect `TestClock` to advance on its own during `Effect.sleep` — it won't.

✅ Fork the sleeping fiber, then call `TestClock.adjust` to unblock it.

❌ Don't share mutable state between `it.effect` tests at module scope — tests may run concurrently.

✅ Use `Ref.make` inside the test or in `beforeEach`.

---

## See also

- `packages/vitest/src/index.ts` — full API (`it`, `layer`, `flakyTest`, `prop`)
- `packages/vitest/test/index.test.ts` — authoritative integration examples
- `packages/effect/src/TestClock.ts` — `adjust`, `setTime`, `sleeps`
- `packages/effect/src/TestContext.ts` — `TestContext`, `live`
- Effect website: https://effect.website/docs/testing
