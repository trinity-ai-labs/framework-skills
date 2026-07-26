# Combinators

## Contents

- [Mapping](#mapping)
- [Sequencing](#sequencing)
- [Combining Multiple Effects](#combining-multiple-effects)
- [`Effect.all` — collect many effects](#effectall-collect-many-effects)
- [`Effect.forEach` — iterate an iterable effectfully](#effectforeach-iterate-an-iterable-effectfully)
- [Conditional Operators](#conditional-operators)
- [Iteration](#iteration)
- [Do Notation](#do-notation)
- [Choosing `gen` vs `.pipe`](#choosing-gen-vs-pipe)
- [See also](#see-also)

---


The building blocks for composing effects into programs.

## Mapping

### `Effect.map` — transform the success value

```ts
import { Effect } from "effect"

const doubled = Effect.map(Effect.succeed(21), (n) => n * 2)
// Effect<number, never, never>

// Pipe style
const doubled2 = Effect.succeed(21).pipe(Effect.map((n) => n * 2))
```

`map` is a pure transformation — the function must be synchronous and cannot fail.

### `Effect.as` — replace success value with a constant

```ts
import { Effect } from "effect"

const unit = Effect.succeed(42).pipe(Effect.as("done"))
// Effect<string, never, never>
```

### `Effect.asVoid` — discard success value

```ts
import { Effect } from "effect"

const discarded = Effect.succeed(42).pipe(Effect.asVoid)
// Effect<void, never, never>
```

---

## Sequencing

### `Effect.flatMap` — sequence effects, pass value forward

```ts
import { Effect } from "effect"

const program = Effect.flatMap(
  Effect.succeed(10),
  (n) => Effect.succeed(n * 2)
)
// Effect<number, never, never>
```

Both E and R channels are unioned: `flatMap` of `Effect<A, E1, R1>` with a function returning `Effect<B, E2, R2>` gives `Effect<B, E1 | E2, R1 | R2>`.

### `Effect.andThen` — the Swiss-army sequencer

`andThen` accepts any of: a value, a function returning a value, a Promise, a function returning a Promise, an Effect, or a function returning an Effect. It selects the right behavior automatically.

```ts
import { Effect } from "effect"

// Pass a plain value (like `as`)
const r1 = Effect.succeed(1).pipe(Effect.andThen("hello"))
// Effect<string, never, never>

// Pass a function returning a value (like `map`)
const r2 = Effect.succeed(1).pipe(Effect.andThen((n) => n + 1))
// Effect<number, never, never>

// Pass an Effect (like `zipRight`)
const r3 = Effect.succeed(1).pipe(Effect.andThen(Effect.succeed("world")))
// Effect<string, never, never>

// Pass a function returning an Effect (like `flatMap`)
const r4 = Effect.succeed(1).pipe(
  Effect.andThen((n) => Effect.succeed(n * 2))
)
// Effect<number, never, never>

// Pass a Promise (wrapped automatically)
const r5 = Effect.succeed(1).pipe(
  Effect.andThen((n) => Promise.resolve(n + 1))
)
// Effect<number, Cause.UnknownException, never>
```

`andThen` is useful in pipelines where the next step might be a value, effect, or Promise. For gen-style code, `yield*` is clearer.

### `Effect.tap` — run a side effect, keep the value

```ts
import { Effect } from "effect"

const program = Effect.succeed(42).pipe(
  Effect.tap((n) => Effect.log(`Got: ${n}`)),
  Effect.map((n) => n * 2)
  // n is still 42 here, tap did not change it
)
```

`tap` accepts the same set of arguments as `andThen` — value, function, Effect, Promise — but always returns the original value. Errors from the tap propagate and abort the pipeline.

```ts
// tap with a non-function value (runs the effect, ignores result)
const program2 = Effect.succeed(1).pipe(
  Effect.tap(Effect.log("step complete"))
)
```

### `Effect.flatten` — remove one layer of nesting

```ts
import { Effect } from "effect"

const nested: Effect.Effect<Effect.Effect<string>> =
  Effect.succeed(Effect.succeed("hello"))

const flat: Effect.Effect<string> = Effect.flatten(nested)
```

Equivalent to `flatMap(identity)`.

---

## Combining Multiple Effects

### `Effect.zip` — run two effects, get both results

```ts
import { Effect } from "effect"

// Sequential (default)
const both = Effect.zip(Effect.succeed(1), Effect.succeed("a"))
// Effect<[number, string], never, never>

// Concurrent
const concurrent = Effect.zip(effectA, effectB, { concurrent: true })
```

### `Effect.zipLeft` / `Effect.zipRight`

```ts
import { Effect } from "effect"

// Keep the left result
const left = Effect.zipLeft(Effect.succeed(1), Effect.succeed("ignored"))
// Effect<number, never, never>

// Keep the right result
const right = Effect.zipRight(Effect.succeed("ignored"), Effect.succeed(2))
// Effect<number, never, never>
```

### `Effect.zipWith` — combine results with a function

```ts
import { Effect } from "effect"

const sum = Effect.zipWith(
  Effect.succeed(2),
  Effect.succeed(3),
  (a, b) => a + b
)
// Effect<number, never, never>
```

---

## `Effect.all` — collect many effects

`all` is the primary multi-effect combinator. Its result type depends on the shape of its input.

### Input shapes

```ts
import { Effect } from "effect"

// Tuple → preserves length and per-position types
const tuple = Effect.all([Effect.succeed(1), Effect.succeed("a")])
// Effect<[number, string], never, never>

// Struct (record) → preserves key types
const struct = Effect.all({ n: Effect.succeed(1), s: Effect.succeed("a") })
// Effect<{ n: number; s: string }, never, never>

// Iterable → returns array
const iter = Effect.all([1, 2, 3].map(Effect.succeed))
// Effect<number[], never, never>
```

### `concurrency` option

```ts
import { Effect } from "effect"

const effects = [fetchUser(1), fetchUser(2), fetchUser(3)]

// Sequential (default — concurrency: 1)
const seq = Effect.all(effects)

// Fixed concurrency
const bounded = Effect.all(effects, { concurrency: 2 })

// Maximum concurrency (all fibers started at once)
const unbounded = Effect.all(effects, { concurrency: "unbounded" })

// Inherit from withConcurrency wrapper
const inherited = Effect.all(effects, { concurrency: "inherit" })
```

Order in the result array always matches the input order, regardless of concurrency.

### `discard` option

```ts
import { Effect } from "effect"

// Run all, return void (collect no results)
const fire = Effect.all(effects, { discard: true })
// Effect<void, never, never>
```

### `mode` option

```ts
import { Effect, Either, Option } from "effect"

const mixed = [Effect.succeed(1), Effect.fail("e"), Effect.succeed(3)]

// "default" (default) — fail-fast on first error
const failFast = Effect.all(mixed)
// fails with "e"

// "either" — never fails; wraps each result in Either
const eithers = Effect.all(mixed, { mode: "either" })
// Effect<[Either<number, string>, Either<never, string>, Either<number, string>]>
// ↑ succeeds with an array of Either values

// "validate" — runs all, collects errors as Option<E> per position
const validated = Effect.all(mixed, { mode: "validate" })
// fails with [Option.none(), Option.some("e"), Option.none()]
// useful for form/batch validation — you see ALL errors
```

### `allWith` — data-last version for pipes

```ts
import { Effect, pipe } from "effect"

const result = pipe(
  [fetchUser(1), fetchUser(2)],
  Effect.allWith({ concurrency: 2 })
)
```

---

## `Effect.forEach` — iterate an iterable effectfully

```ts
import { Effect } from "effect"

const ids = [1, 2, 3]

// Collect results (default)
const users = Effect.forEach(ids, (id) => fetchUser(id))
// Effect<User[], FetchError, never>

// Concurrent
const concurrent = Effect.forEach(ids, fetchUser, { concurrency: 2 })

// Discard results (side-effect-only)
const logged = Effect.forEach(
  ids,
  (id) => Effect.log(`processing ${id}`),
  { discard: true }
)
// Effect<void, never, never>
```

The callback receives `(element, index)`.

---

## Conditional Operators

### `Effect.when` — run effect if condition is true

```ts
import { Effect } from "effect"

// Returns Option.some(result) if condition is true, Option.none() otherwise
const result = Effect.succeed(42).pipe(
  Effect.when(() => someFlag)
)
// Effect<Option.Option<number>, never, never>
```

### `Effect.unless` — inverse of `when`

```ts
import { Effect } from "effect"

const result = Effect.succeed(42).pipe(
  Effect.unless(() => shouldSkip)
)
// Effect<Option.Option<number>, never, never>
```

### `Effect.whenEffect` / `Effect.unlessEffect` — condition is itself an effect

```ts
import { Effect, Random } from "effect"

const randomInt = Random.nextInt.pipe(
  Effect.whenEffect(Random.nextBoolean)
)
// Effect<Option.Option<number>, never, never>
```

---

## Iteration

### `Effect.loop` — stateful while-loop

```ts
import { Effect } from "effect"

// Collect results (discard: false, the default)
const result = Effect.loop(1, {
  while: (state) => state <= 5,
  step: (state) => state + 1,
  body: (state) => Effect.succeed(state * state)
})
// Effect<number[], never, never> → [1, 4, 9, 16, 25]

// Side-effect only (discard: true)
const sideEffect = Effect.loop(0, {
  while: (i) => i < 3,
  step: (i) => i + 1,
  body: (i) => Effect.log(`step ${i}`),
  discard: true
})
// Effect<void, never, never>
```

### `Effect.iterate` — advance until condition fails

```ts
import { Effect } from "effect"

// Like a while loop that returns the final state
const final = Effect.iterate(0, {
  while: (n) => n < 10,
  body: (n) => Effect.succeed(n + 1)
})
// Effect<number, never, never> → 10
```

---

## Do Notation

For pipelines where you can't use `gen` (e.g., inside an existing pipe chain), Do notation provides named bindings that accumulate into an object.

```ts
import { Effect, pipe } from "effect"

const result = pipe(
  Effect.Do,
  Effect.bind("x", () => Effect.succeed(2)),
  Effect.bind("y", () => Effect.succeed(3)),
  Effect.let("sum", ({ x, y }) => x + y),
  Effect.map(({ x, y, sum }) => `${x} + ${y} = ${sum}`)
)
// Effect<string, never, never>

Effect.runSync(result) // => "2 + 3 = 5"
```

- `Effect.Do` — `Effect<{}>`, the empty accumulator
- `Effect.bind(name, f)` — runs `f(acc)` and adds result at `name`
- `Effect.let(name, f)` — pure computation, no Effect
- `Effect.bindTo(name)` — wraps an existing Effect's value into `{ name: value }`
- `Effect.bindAll({ ... }, options)` — runs a record of effects via `Effect.all`, binds all keys

```ts
import { Effect, pipe } from "effect"

// bindAll combines bind + all — useful for concurrent Do steps
const concurrent = pipe(
  Effect.Do,
  Effect.bind("userId", () => Effect.succeed(1)),
  Effect.bindAll(({ userId }) => ({
    user: fetchUser(userId),
    settings: fetchSettings(userId)
  }), { concurrency: 2 })
)
// Effect<{ userId: number; user: User; settings: Settings }, FetchError, never>
```

---

## Choosing `gen` vs `.pipe`

| Use `gen` when | Use `.pipe` when |
|----------------|-----------------|
| Multiple sequential steps with local variables | Short single-value transformation |
| Branching logic (if/else based on yielded values) | Composing a reusable operator |
| Loops (you need `loop` or `iterate` anyway) | Building library-style middleware |
| You need to `yield*` and inspect intermediate results | A single `map` or `tap` is sufficient |
| Readability matters more than point-free style | Point-free style aids clarity |

Both styles are equally first-class. There is no performance difference.

```ts
import { Effect } from "effect"

// gen style — clear, sequential
const program1 = Effect.gen(function* () {
  const a = yield* fetchA()
  const b = yield* fetchB(a.id)
  return { a, b }
})

// pipe style — concise for simple chains
const program2 = fetchA().pipe(
  Effect.flatMap((a) =>
    fetchB(a.id).pipe(Effect.map((b) => ({ a, b })))
  )
)
```

---

## See also

- [01-mental-model.md](01-mental-model.md) — the three-channel type and lazy descriptions
- [02-creating-running.md](02-creating-running.md) — constructors and running at the edge
