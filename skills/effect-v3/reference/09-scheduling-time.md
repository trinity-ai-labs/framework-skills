# 09 — Scheduling & Time

When you reach for this: you need to retry a failing effect (`Effect.retry`), repeat a successful one (`Effect.repeat`), add delays between runs, schedule recurring tasks with cron expressions, use Effect-native time primitives instead of `Date.now`/`setTimeout`, memoize expensive effects with a TTL, or rate-limit calls to a resource.

---

## Contents

- [`Schedule<Out, In, R>` — the type](#scheduleout-in-r-the-type)
- [Base schedules](#base-schedules)
- [Combinators](#combinators)
- [Applying schedules](#applying-schedules)
- [Time: `Effect.sleep`, `Effect.delay`, `Effect.timeout`](#time-effectsleep-effectdelay-effecttimeout)
- [`Clock` — testable time](#clock-testable-time)
- [`Duration` — time values](#duration-time-values)
- [`Cron` — cron expressions](#cron-cron-expressions)
- [Caching](#caching)
- [`RateLimiter` — calls per window](#ratelimiter-calls-per-window)
- [Common patterns](#common-patterns)
- [`Schedule` quick reference](#schedule-quick-reference)
- [See also](#see-also)


## `Schedule<Out, In, R>` — the type

```
Schedule<Out, In, R>
         │    │   └─ requirements (services needed)
         │    └─ input type (what the schedule consumes)
         └─ output type (what each step produces)
```

- For **retry**: `In = E` (error), each step receives the failure.
- For **repeat**: `In = A` (success value), each step receives the result.
- `R` is the requirement; most built-in schedules have `R = never`.

A `Schedule` is a **description** — it has no side effects until you attach it to an effect.

---

## Base schedules

### Recurrence

```ts
import { Schedule } from "effect"

Schedule.recurs(3)         // run up to 3 more times (not counting the first)
Schedule.once              // recur exactly once (then stop)
Schedule.forever           // recur indefinitely, output: 0, 1, 2, …
Schedule.stop              // never recur (single attempt)
```

### Time-based

```ts
Schedule.spaced("500 millis")      // constant delay between end of one run and start of next
Schedule.fixed("1 second")         // fixed interval from start time (avoids drift)
Schedule.windowed("10 seconds")    // align to window boundaries on the clock
Schedule.exponential("100 millis") // 100ms, 200ms, 400ms, 800ms, … (default factor 2.0)
Schedule.exponential("100 millis", 1.5)  // custom factor
Schedule.fibonacci("1 second")     // 1s, 1s, 2s, 3s, 5s, 8s, …
Schedule.linear("100 millis")      // 100ms, 200ms, 300ms, 400ms, …
```

### Cron

```ts
import { Schedule, Cron } from "effect"

// cron expression string (seconds field optional)
Schedule.cron("0 * * * *")                      // top of every hour
Schedule.cron("0 9 * * 1-5")                    // 9am Mon–Fri
Schedule.cron("*/30 * * * * *")                 // every 30 seconds (6-field with seconds)
Schedule.cron("0 0 * * *", "America/New_York")  // midnight ET

// or pre-parsed Cron value
const myCron = Cron.parse("0 9 * * 1-5")  // returns Either
Schedule.cron(myCron._tag === "Right" ? myCron.right : /* fallback */)

// convenience cron helpers
Schedule.secondOfMinute(15)   // every minute at :15
Schedule.minuteOfHour(0)      // top of every hour
Schedule.hourOfDay(9)         // 9am daily
Schedule.dayOfMonth(1)        // 1st of every month
Schedule.dayOfWeek(1)         // every Monday (0 = Sunday)
```

`Schedule.cron` output is `[number, number]` (previous fire time, current fire time in ms).

---

## Combinators

### Timing & delays

```ts
import { Schedule, Duration } from "effect"

// add extra delay after each output
Schedule.recurs(5).pipe(
  Schedule.addDelay(() => "100 millis")
)

// mutate the computed delay based on output and original delay
Schedule.exponential("1 second").pipe(
  Schedule.modifyDelay((out, delay) => Duration.min(delay, Duration.seconds(30)))  // cap at 30s
)

// jitter: randomise delay ±20% (default), reduces thundering herd
Schedule.exponential("1 second").pipe(Schedule.jittered)
// custom jitter range
Schedule.exponential("1 second").pipe(Schedule.jitteredWith({ min: 0.5, max: 1.5 }))
```

### Stopping conditions

```ts
// stop based on output value
Schedule.forever.pipe(Schedule.whileOutput((n) => n < 10))         // stops when output >= 10
Schedule.forever.pipe(Schedule.untilOutput((n) => n >= 10))        // stops when output >= 10
Schedule.forever.pipe(Schedule.recurWhile((n: number) => n < 10))  // same
Schedule.forever.pipe(Schedule.recurUntil((n: number) => n >= 10)) // same

// stop based on input value (error in retry, value in repeat)
Schedule.recurs(10).pipe(Schedule.whileInput((e: Error) => e.message !== "fatal"))
Schedule.recurs(10).pipe(Schedule.untilInput((e: Error) => e.message === "fatal"))

// stop based on TOTAL elapsed time — a wall-clock budget for the whole schedule
Schedule.exponential("100 millis").pipe(Schedule.upTo("30 seconds"))
Schedule.recurUpTo("30 seconds")   // standalone: recur until 30s have passed, outputs elapsed
Schedule.elapsed                    // standalone: recurs forever, outputs time since the first step
```

⚠️ **A delay cap is not a time budget.** `modifyDelay(… Duration.min(d, "30 seconds"))` caps how long each individual *wait* is — the schedule then runs forever, 30 seconds at a time. `upTo("30 seconds")` caps the *total*. They're routinely confused; you usually want both.

### Composition

```ts
// intersect (&&): continue only if BOTH want to; use the LONGER delay
const retryPolicy =
  Schedule.recurs(5).pipe(
    Schedule.intersect(Schedule.exponential("100 millis"))
  )

// union (||): continue if EITHER wants to; use the SHORTER delay
const aggressiveRetry =
  Schedule.recurs(3).pipe(
    Schedule.union(Schedule.spaced("10 seconds"))
  )

// andThen (sequential): run first to completion, then switch to second
const backoffThenFixed =
  Schedule.exponential("100 millis").pipe(
    Schedule.intersect(Schedule.recurs(5)),   // exponential for first 5
    Schedule.andThen(Schedule.spaced("5 seconds"))  // then steady 5s
  )

// compose: pipe output of one schedule as input to another
const piped = Schedule.recurs(5).pipe(
  Schedule.compose(Schedule.elapsed)  // output elapsed time
)
```

### Observability & mapping

```ts
// tap output — run effect for each step output, doesn't change schedule
Schedule.exponential("1 second").pipe(
  Schedule.tapOutput((delay) => Effect.log(`retrying in ${Duration.toMillis(delay)}ms`))
)

// map output
Schedule.recurs(5).pipe(Schedule.map((n) => `attempt ${n + 1}`))

// mapInput — transform the input before the schedule sees it
Schedule.recurs(5).pipe(Schedule.mapInput((e: Error) => e.message))
```

---

## Applying schedules

### `Effect.retry` — on failure

```ts
import { Effect, Schedule } from "effect"

const flaky = Effect.gen(function* () {
  // might fail
})

// with a Schedule
const retried = Effect.retry(flaky, Schedule.exponential("100 millis").pipe(
  Schedule.intersect(Schedule.recurs(3))
))

// shorthand options object
const retried2 = Effect.retry(flaky, {
  times: 3,                              // simple count shorthand
})
const retried3 = Effect.retry(flaky, {
  schedule: Schedule.exponential("200 millis"),
  times: 5,                              // caps retries even if schedule would continue
  while: (e: Error) => e.message !== "fatal",  // stop retrying on fatal
})

// with fallback
const retried4 = Effect.retryOrElse(
  flaky,
  Schedule.recurs(3).pipe(Schedule.addDelay(() => "500 millis")),
  (error, lastScheduleOutput) => Effect.succeed("default")  // fallback
)
```

> `retry` feeds **errors** as the schedule input. The schedule's output is the number of retries so far (or whatever the schedule produces).

### `Effect.repeat` — on success

```ts
// run forever at a fixed interval
const heartbeat = Effect.repeat(
  sendPing,
  Schedule.spaced("30 seconds")
)

// repeat N more times
const repeated = Effect.repeat(flaky, Schedule.recurs(4))  // runs 5 times total

// shorthand
const repeated2 = Effect.repeat(sendEvent, { times: 3 })

// with fallback on failure
const safe = Effect.repeatOrElse(
  sendPing,
  Schedule.spaced("10 seconds"),
  (error, _scheduleOutput) => Effect.log("ping failed, giving up")
)
```

> `repeat` feeds **success values** as the schedule input. The final value of `Effect.repeat` is the **schedule's last output** (not the effect's last value).

### `Effect.schedule`

Like `repeat` but drives the schedule entirely, returning the schedule's final output value even if the effect's output is irrelevant:

```ts
const program = Effect.schedule(
  sendPing,
  Schedule.spaced("1 second").pipe(Schedule.intersect(Schedule.recurs(9)))
)
// runs 10 times total, returns last schedule output
```

### `Effect.repeatN`

```ts
// run effect n additional times (simple, no schedule overhead)
const thrice = Effect.repeatN(doWork, 2)  // runs 3 times total
```

---

## Time: `Effect.sleep`, `Effect.delay`, `Effect.timeout`

### Sleep and delay

```ts
import { Effect, Duration } from "effect"

// pause fiber — does NOT block the OS thread
yield* Effect.sleep("2 seconds")
yield* Effect.sleep(Duration.seconds(2))
yield* Effect.sleep(2000)           // number = millis

// add delay before an effect's result
const delayedFetch = fetchData.pipe(Effect.delay("100 millis"))
```

❌ Don't use `setTimeout` or `Date.now()` directly — they bypass `TestClock` and can't be controlled in tests.
✅ Always use `Effect.sleep` / `Clock.currentTimeMillis`.

### Timeout

```ts
// fail with TimeoutException if effect doesn't complete in time
const bounded = Effect.timeout(longTask, "5 seconds")
// type: Effect<A, TimeoutException | E, R>

// return None instead of failing
const gentle = Effect.timeoutOption(longTask, "5 seconds")
// type: Effect<Option<A>, E, R>

// custom fallback on timeout
const withFallback = Effect.timeoutTo(longTask, {
  duration: "5 seconds",
  onTimeout: Effect.succeed("cached"),
  onSuccess: (a) => Effect.succeed(a)
})
```

---

## `Clock` — testable time

```ts
import { Clock, Effect } from "effect"

// get current wall time (testable — uses Clock service)
const nowMs  = yield* Clock.currentTimeMillis  // Effect<number>
const nowNs  = yield* Clock.currentTimeNanos   // Effect<bigint>

// low-level — run an effect with access to the Clock service
yield* Clock.clockWith((clock) => clock.sleep(Duration.seconds(1)))
```

### TestClock for deterministic time tests

```ts
import { Effect, TestClock, TestServices, Duration, Fiber } from "effect"
import * as it from "@effect/vitest"

it.effect("timeout fires after sleep", () =>
  Effect.gen(function* () {
    // fork the effect under test
    const fiber = yield* Effect.fork(
      Effect.sleep("1 minute").pipe(Effect.timeout("30 seconds"))
    )

    // advance synthetic time — no real waiting
    yield* TestClock.adjust("1 minute")

    const result = yield* Fiber.join(fiber)
    // result is Either.Left(TimeoutException)
  }).pipe(Effect.provide(TestServices.liveLayer()))
)
```

`TestClock.adjust(duration)` advances the synthetic clock by `duration`, triggering all pending `sleep`s that fall within that window — deterministic and fast.

> TestClock is in `effect/TestClock`. Use `TestServices.liveLayer()` or `@effect/vitest`'s `it.effect` helper to inject it in tests.

---

## `Duration` — time values

`Duration` is the canonical representation for time spans. It replaces raw millisecond numbers everywhere in Effect.

### Constructors

```ts
import { Duration } from "effect"

// preferred string form (DurationInput)
"500 millis"
"2 seconds"
"1 minutes"
"3 hours"
"7 days"
"1 weeks"

// explicit constructors
Duration.millis(500)
Duration.seconds(2)
Duration.minutes(1)
Duration.hours(3)
Duration.days(7)
Duration.weeks(1)
Duration.nanos(1_000_000n)   // bigint
Duration.micros(1000n)       // bigint

// constants
Duration.zero
Duration.infinity
```

All of `Effect.sleep`, `Effect.delay`, `Schedule.*`, `Effect.timeout` accept `DurationInput` which is `Duration | number (millis) | bigint (nanos) | [seconds, nanos] | "N unit"`.

### Arithmetic & comparison

```ts
const a = Duration.seconds(5)
const b = Duration.seconds(3)

Duration.sum(a, b)              // 8 seconds
Duration.subtract(a, b)        // 2 seconds  (note: subtract, not minus)
Duration.times(a, 4)            // 20 seconds
Duration.divide(a, 2)           // 2.5 seconds (returns Option<Duration>)

Duration.lessThan(a, b)         // false
Duration.greaterThan(a, b)      // true
Duration.equals(a, a)           // true
Duration.min(a, b)              // 3 seconds
Duration.max(a, b)              // 5 seconds
Duration.clamp(a, { minimum: b, maximum: Duration.seconds(10) })

Duration.toMillis(a)            // 5000
Duration.toSeconds(a)           // 5
Duration.toNanos(a)             // Option<bigint>

Duration.format(a)              // human-readable string
```

---

## `Cron` — cron expressions

```ts
import { Cron, Either } from "effect"

// parse a cron expression (5-field standard or 6-field with seconds)
const result = Cron.parse("*/5 * * * *")    // Either<ParseError, Cron>
// or with timezone
const tz = Cron.parse("0 9 * * 1-5", "Europe/London")

// check if a date matches
const cron = Either.getOrThrow(Cron.parse("0 9 * * *"))
Cron.match(cron, new Date())

// next occurrence
Cron.next(cron, new Date())  // Option<Date>
```

For recurring effects use `Schedule.cron(expression)` which wraps `Cron` automatically.

---

## Caching

### `Effect.cached` — permanent memoize

```ts
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const expensiveTask = Effect.gen(function* () {
    yield* Effect.sleep("100 millis")
    return Math.random()
  })

  // cached returns Effect<Effect<A>> — the inner Effect is the memoized one
  const memo = yield* Effect.cached(expensiveTask)

  const a = yield* memo   // runs the task
  const b = yield* memo   // returns cached result instantly
  // a === b
})
```

### `Effect.cachedWithTTL` — TTL-based memoize

```ts
const program = Effect.gen(function* () {
  const cachedFetch = yield* Effect.cachedWithTTL(fetchData, "5 seconds")

  yield* cachedFetch   // runs
  yield* cachedFetch   // cached (< 5s later)
  yield* Effect.sleep("5 seconds")
  yield* cachedFetch   // cache expired, runs again
})
```

### `Effect.cachedInvalidateWithTTL` — memoize with manual invalidation

```ts
const program = Effect.gen(function* () {
  const [cachedFetch, invalidate] = yield* Effect.cachedInvalidateWithTTL(fetchData, "1 minute")

  yield* cachedFetch   // runs
  yield* invalidate    // force expiry before TTL
  yield* cachedFetch   // runs again
})
```

### `Effect.cachedFunction` — memoize a function

```ts
const program = Effect.gen(function* () {
  const cachedGet = yield* Effect.cachedFunction(
    (key: string) => lookupInDatabase(key)
  )

  const a = yield* cachedGet("user-1")
  const b = yield* cachedGet("user-1")   // cached, no DB call
  // a === b
})
```

Uses structural equality (`Equal`) for key comparison by default. Pass a custom `Equivalence` as the second arg.

### `Effect.once` — run at most once

```ts
const program = Effect.gen(function* () {
  // once returns Effect<Effect<void, E, R>>
  // the inner effect runs only on first invocation
  const initialize = yield* Effect.once(runMigrations)

  yield* initialize   // runs
  yield* initialize   // no-op
  yield* initialize   // no-op
})
```

---

## `RateLimiter` — calls per window

```ts
import { Effect, RateLimiter } from "effect"
import { compose } from "effect/Function"

const program = Effect.scoped(
  Effect.gen(function* () {
    // token-bucket: spreads requests evenly over the interval
    const perSecond = yield* RateLimiter.make({
      limit: 10,
      interval: "1 seconds",
      algorithm: "token-bucket"   // default
    })

    // fixed-window: resets counter each interval
    const perMinute = yield* RateLimiter.make({
      limit: 100,
      interval: "1 minutes",
      algorithm: "fixed-window"
    })

    // compose limiters — both constraints respected
    const rateLimit = compose(perSecond, perMinute)

    // wrap any effect
    yield* rateLimit(callExternalApi())

    // per-call cost (for credit-based limits)
    yield* perMinute(
      callExpensiveEndpoint().pipe(RateLimiter.withCost(5))
    )
  })
)
```

> `RateLimiter` requires `Scope` — use `Effect.scoped` to manage its lifetime. Only the **start** of each effect is rate-limited; concurrent in-flight executions are not bounded (use `Semaphore` for that).

---

## Common patterns

### Exponential backoff with jitter and cap

```ts
import { Schedule, Duration } from "effect"

const retryPolicy = Schedule.exponential("100 millis").pipe(
  Schedule.jittered,                                              // ±20% random
  Schedule.modifyDelay((_, d) => Duration.min(d, Duration.seconds(30))),  // per-wait cap
  Schedule.intersect(Schedule.recurs(10)),                        // max 10 retries
  Schedule.upTo("2 minutes")                                      // total time budget
)

const result = Effect.retry(unreliableEffect, retryPolicy)
```

### Retry a specific tagged error only, within a total budget

Filter on the *input* (the error) and bound the whole thing with `upTo` — anything the predicate rejects fails through immediately, unretried.

```ts
const fetchUser = Effect.retry(
  callApi,   // fails with NetworkError | NotFoundError
  Schedule.exponential("100 millis").pipe(
    Schedule.jittered,
    Schedule.whileInput((e: NetworkError | NotFoundError) => e._tag === "NetworkError"),
    Schedule.upTo("30 seconds")
  )
)
```

To log every attempt, tap the error channel *before* retrying — `Effect.retry` re-runs whatever it wraps, so the tap fires once per failed attempt:

```ts
const withLogging = callApi.pipe(
  Effect.tapErrorTag("NetworkError", (e) => Effect.logWarning(`retrying after ${e._tag}`))
)
```

The predicate is just a predicate — filter on anything the error carries, not only `_tag`:

```ts
Schedule.whileInput((e: ApiError) => e.status === 429 || e.status >= 500)   // retry throttling + 5xx
```

For a small policy, the options form of `Effect.retry` reads better than building a `Schedule`: `Effect.retry(callApi, { times: 5, while: (e) => e._tag === "NetworkError" })`.

### Heartbeat that logs its iteration

```ts
const heartbeat = Effect.repeat(
  sendPing,
  Schedule.spaced("30 seconds").pipe(
    Schedule.tapOutput((n) => Effect.log(`ping #${n}`))
  )
)
```

### Guaranteed one-time initialization

```ts
const startup = Effect.gen(function* () {
  const migrate = yield* Effect.once(runMigrations)
  // safe to call from multiple places — only runs once
  yield* Effect.all([migrate, migrate, migrate])
})
```

---

## `Schedule` quick reference

| Constructor | Output | Notes |
|---|---|---|
| `recurs(n)` | `number` | n additional attempts |
| `once` | `void` | one recurrence |
| `forever` | `number` | 0, 1, 2, … |
| `stop` | `void` | never recurs |
| `spaced(d)` | `number` | delay from end of last run |
| `fixed(d)` | `number` | delay from start of last run |
| `windowed(d)` | `number` | align to window |
| `exponential(base, factor?)` | `Duration` | geometric backoff |
| `fibonacci(one)` | `Duration` | fibonacci delays |
| `linear(base)` | `Duration` | linear backoff |
| `cron(expr)` | `[number, number]` | cron expression |
| `elapsed` | `Duration` | recurs forever, outputs time since first step |
| `recurUpTo(d)` | `Duration` | recurs until `d` has elapsed in total |

| Combinator | Description |
|---|---|
| `intersect(s)` / `&&` operator | both must continue; longer delay |
| `union(s)` / `||` operator | either continues; shorter delay |
| `andThen(s)` | sequential — first finishes, then second |
| `compose(s)` | pipe output to next schedule's input |
| `addDelay(f)` | extra delay per step |
| `modifyDelay(f)` | override computed delay |
| `jittered` | ±20% random noise on delay |
| `whileInput(pred)` | stop when pred returns false |
| `whileOutput(pred)` | stop when pred returns false |
| `untilInput(pred)` | stop when pred returns true |
| `untilOutput(pred)` | stop when pred returns true |
| `upTo(d)` | stop once `d` has elapsed in total |
| `recurWhile(pred)` | alias for `whileOutput` |
| `recurUntil(pred)` | alias for `untilOutput` |
| `tapOutput(f)` | side-effect on each output |
| `mapInput(f)` | transform input |
| `map(f)` | transform output |

---

## See also

- `08-state-coordination.md` — `Ref`, `Semaphore`, `Latch`, `Deferred`
- `07-concurrency-fibers.md` — `Effect.fork`, `Fiber`
- `packages/effect/src/TestClock.ts` — `adjust`, `setTime`, `sleeps`
- `packages/effect/test/Effect/caching.test.ts`
- `packages/effect/test/Cron.test.ts`
- https://effect.website/docs/scheduling/introduction
