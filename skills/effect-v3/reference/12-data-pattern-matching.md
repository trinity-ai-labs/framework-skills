# Data, Option, Either & Pattern Matching — Effect v3

When you reach for this: representing optional values without null, typed error channels without exceptions, discriminated unions with exhaustive matching, nominal types, structural equality, and persistent functional collections.

---

## Contents

- [Option](#option)
- [Either](#either)
- [Data Module](#data-module)
- [Equal & Hash](#equal-hash)
- [Brand — Nominal Types](#brand-nominal-types)
- [Match Module](#match-module)
- [Persistent Collections](#persistent-collections)
- [Functional Data Utilities](#functional-data-utilities)
- [Function Utilities](#function-utilities)
- [Patterns](#patterns)
- [See also](#see-also)


## Option

`Option<A>` is either `Some<A>` (a value) or `None` (absent). Use it for partial functions, optional struct fields, and results that are legitimately empty (not erroneous).

```ts
import { Option } from "effect"

// Constructors
const a = Option.some(42)      // Option<number> = Some { value: 42 }
const b = Option.none<number>() // Option<number> = None

// From nullable
Option.fromNullable(null)       // None
Option.fromNullable(undefined)  // None
Option.fromNullable("hello")    // Some("hello")

// From an iterable — wraps first element
Option.fromIterable([1, 2, 3])  // Some(1)
Option.fromIterable([])          // None
```

### Getting values out

```ts
Option.getOrElse(opt, () => 0)      // A | 0
Option.getOrNull(opt)                // A | null
Option.getOrUndefined(opt)           // A | undefined
Option.getOrThrow(opt)               // A — throws if None
Option.getOrThrowWith(opt, () => new Error("empty"))
```

### Transformation

```ts
Option.map(opt, (n) => n * 2)          // Option<number>
Option.flatMap(opt, (n) => n > 0 ? Option.some(n) : Option.none())
Option.filter(opt, (n) => n > 0)       // None if predicate fails
Option.orElse(opt, () => Option.some(99))
Option.orElseSome(opt, () => 99)       // wraps fallback in Some
```

### Pattern matching

```ts
Option.match(opt, {
  onNone: () => "nothing",
  onSome: (n) => `got ${n}`,
})
```

### Guards

```ts
Option.isSome(opt)   // opt is Some<A>
Option.isNone(opt)   // opt is None<A>
Option.isOption(x)   // x is Option<unknown>
```

### Conversion

```ts
Option.getRight(either)  // Option<A> from Either<A, E>
Option.getLeft(either)   // Option<E> from Either<A, E>
Option.toRefinement(fn)  // turns (a: A) => Option<B extends A> into a type guard
```

### Option inside `Effect.gen`

`Option` is **not** an `Effect`, but you can lift it:

```ts
import { Effect, Option } from "effect"

const program = Effect.gen(function*() {
  const value = yield* Effect.fromNullable(maybeNull)
  // fails with NoSuchElementException if null/undefined

  // Or unwrap manually:
  const opt = Option.fromNullable(maybeNull)
  if (Option.isNone(opt)) yield* Effect.fail("not found")
  const n = opt.value
})
```

---

## Either

`Either<A, E>` is `Right<A>` (success) or `Left<E>` (error). Use it when a function can fail with a typed error but you want a **pure** (non-Effect) computation.

```ts
import { Either } from "effect"

Either.right(42)      // Either<number, never>
Either.left("oops")   // Either<never, string>

// From nullable
Either.fromNullable(value, () => "was null")
// Right(value) if non-null, Left("was null") otherwise

// From Option
Either.fromOption(opt, () => "missing")

// Try/catch
Either.try(() => JSON.parse(raw))                  // Either<A, unknown>
Either.try({ try: () => JSON.parse(raw), catch: (e) => String(e) })
```

### Pattern matching

```ts
Either.match(either, {
  onLeft:  (e) => `error: ${e}`,
  onRight: (a) => `ok: ${a}`,
})
```

### Transformation

```ts
Either.map(either, (n) => n * 2)
Either.mapLeft(either, (e) => `wrapped: ${e}`)
Either.mapBoth(either, { onLeft: f, onRight: g })
Either.flatMap(either, (a) => a > 0 ? Either.right(a) : Either.left("negative"))
Either.orElse(either, (e) => Either.right(0))
Either.getOrElse(either, (e) => 0)
Either.getOrThrow(either)            // throws Left value if Left
Either.getOrThrowWith(either, (e) => new Error(String(e)))
```

### Guards

```ts
Either.isRight(e)   // e is Right<E, A>
Either.isLeft(e)    // e is Left<E, A>
Either.isEither(x)  // x is Either<unknown, unknown>
```

### Either inside `Effect.gen`

`Either<A, E>` can be yielded directly in `Effect.gen`:

```ts
const program = Effect.gen(function*() {
  const n = yield* Either.right(42)      // n: number
  const x = yield* Either.left("bad")    // short-circuits with "bad" as error
})
// Effect<number, string, never>
```

---

## Data Module

`Data` provides constructors for **structurally equal** objects. Two `Data.struct` values with identical fields are `Equal.equals`-equal even though they are different object references.

### `Data.struct`

```ts
import { Data, Equal } from "effect"

const alice1 = Data.struct({ name: "Alice", age: 30 })
const alice2 = Data.struct({ name: "Alice", age: 30 })
Equal.equals(alice1, alice2)  // true
Equal.equals(alice1, { name: "Alice", age: 30 })  // false (plain object)
```

### `Data.tuple` / `Data.array`

```ts
const pair1 = Data.tuple("Alice", 30)
const pair2 = Data.tuple("Alice", 30)
Equal.equals(pair1, pair2)  // true

const arr = Data.array([1, 2, 3])
```

### `Data.case` — structural constructor factory

```ts
interface Person { readonly name: string }

const Person = Data.case<Person>()

const p1 = Person({ name: "Alice" })
const p2 = Person({ name: "Alice" })
Equal.equals(p1, p2)  // true
```

### `Data.tagged` — tagged case

```ts
interface AdminUser {
  readonly _tag: "AdminUser"
  readonly name: string
}
const AdminUser = Data.tagged<AdminUser>("AdminUser")

const u = AdminUser({ name: "Alice" })
u._tag  // "AdminUser"
```

### `Data.Class` — structural equality for classes

```ts
class Person extends Data.Class<{ name: string; age: number }> {
  greet() { return `Hi, I'm ${this.name}` }
}

const p1 = new Person({ name: "Alice", age: 30 })
const p2 = new Person({ name: "Alice", age: 30 })
Equal.equals(p1, p2)  // true
```

### `Data.TaggedClass`

```ts
class AdminUser extends Data.TaggedClass("AdminUser")<{ name: string }> {}

const u = new AdminUser({ name: "Alice" })
u._tag  // "AdminUser"
```

### `Data.taggedEnum` — discriminated union factory

```ts
import { Data } from "effect"

type HttpError = Data.TaggedEnum<{
  BadRequest: { readonly status: 400; readonly message: string }
  NotFound:   { readonly status: 404; readonly message: string }
}>

const { BadRequest, NotFound, $is, $match } = Data.taggedEnum<HttpError>()

const err: HttpError = NotFound({ status: 404, message: "Not Found" })

// $is — type guard
$is("NotFound")(err)   // true
$is("BadRequest")(err) // false

// $match — exhaustive match
$match(err, {
  BadRequest: (e) => `400: ${e.message}`,
  NotFound:   (e) => `404: ${e.message}`,
})
```

**Why `taggedEnum` over plain union?**
- Constructors set `_tag` automatically
- `$is` / `$match` are generated
- Values have structural equality (backed by `Data.tagged`)

### `Data.Error` / `Data.TaggedError`

```ts
class AppError extends Data.Error<{ message: string; code: number }> {}

class NetworkError extends Data.TaggedError("NetworkError")<{
  url: string
  status: number
}> {}

// Both are yieldable in Effect.gen:
yield* new NetworkError({ url: "/api", status: 503 })
```

---

## Equal & Hash

Effect's structural equality protocol. Any object implementing `Equal` can participate.

```ts
import { Equal, Hash, Data } from "effect"

Equal.equals(a, b)        // boolean — uses [Equal.symbol]
Equal.equivalence<A>()    // Equivalence<A> backed by Equal.equals

// Check if something implements Equal
Equal.isEqual(x)

// Hash utilities
Hash.hash(value)          // number
Hash.string("hello")      // number
Hash.number(42)           // number
Hash.array([1, 2, 3])     // number
Hash.combine(h1, h2)      // number
```

### When to use `Equal.equals` vs `===`

| Use `===` | Use `Equal.equals` |
|-----------|-------------------|
| Primitives | `Data.struct`, `Data.Class` instances |
| Objects where reference identity matters | Effect `Chunk`, `HashMap`, `HashSet` |
| Performance-sensitive inner loops | Domain objects that should compare by value |

---

## Brand — Nominal Types

Branded types prevent accidental mixing of values with the same underlying type but different semantics.

### `Brand.nominal` — zero runtime cost

```ts
import { Brand } from "effect"

type UserId = number & Brand.Brand<"UserId">
const UserId = Brand.nominal<UserId>()

const id: UserId = UserId(42)
// id has the same runtime value but a different TypeScript type
```

### `Brand.refined` — with runtime validation

```ts
type PositiveInt = number & Brand.Brand<"PositiveInt">
const PositiveInt = Brand.refined<PositiveInt>(
  (n) => Number.isInteger(n) && n > 0,
  (n) => Brand.error(`Expected positive integer, got ${n}`)
)

PositiveInt(5)      // 5 as PositiveInt
PositiveInt(-1)     // throws BrandErrors
PositiveInt.option(-1)    // None
PositiveInt.either(-1)    // Left(BrandErrors)
PositiveInt.is(5)         // true
```

### `Brand.all` — combine multiple brands

```ts
type SafeId = number & Brand.Brand<"Int"> & Brand.Brand<"Positive">
const SafeId = Brand.all(PositiveInt, IntBrand)
```

### Brand in Schema

```ts
import { Schema } from "effect"

const UserIdSchema = Schema.Number.pipe(Schema.brand("UserId"))
type UserId = typeof UserIdSchema.Type  // number & Brand<"UserId">
```

---

## Match Module

Type-safe pattern matching with compile-time exhaustiveness checking. Think of it as a `switch` statement that TypeScript actually knows is complete.

### Two ways to create a matcher

```ts
import { Match } from "effect"

// 1. Match.type<T>() — returns a reusable function
const matchStatus = Match.type<"active" | "inactive" | "pending">().pipe(
  Match.when("active",   () => "green"),
  Match.when("inactive", () => "red"),
  Match.when("pending",  () => "yellow"),
  Match.exhaustive  // compile error if any case missing
)
matchStatus("active")  // "green"

// 2. Match.value(x) — match a specific value inline
const result = Match.value(someStatus).pipe(
  Match.when("active",   () => "green"),
  Match.orElse(() => "grey")
)
```

### `Match.when` — conditions

Patterns can be:
- Literal values: `"active"`, `42`, `true`
- Predicate functions: `(n) => n > 0`
- Refinements: `Match.string`, `Match.number`, `Match.boolean`
- Partial object shapes: `{ status: "active" }`
- Nested patterns: `{ user: { role: "admin" } }`

```ts
const match = Match.type<{ age: number; role: string }>().pipe(
  Match.when({ age: (n) => n >= 18, role: "admin" }, (_) => "admin"),
  Match.when({ age: (n) => n >= 18 },                (_) => "adult"),
  Match.orElse((_) => "minor")
)
```

### `Match.tag` — discriminated union on `_tag`

```ts
type Event =
  | { _tag: "Login";  userId: string }
  | { _tag: "Logout"; userId: string }
  | { _tag: "Error";  message: string }

const handleEvent = Match.type<Event>().pipe(
  Match.tag("Login",  (e) => `${e.userId} logged in`),
  Match.tag("Logout", (e) => `${e.userId} logged out`),
  Match.tag("Error",  (e) => `Error: ${e.message}`),
  Match.exhaustive
)
```

### `Match.not` — inverse match

```ts
const match = Match.type<string | number>().pipe(
  Match.not("forbidden", (v) => `allowed: ${v}`),
  Match.orElse(() => "forbidden!")
)
```

### `Match.whenOr` / `Match.whenAnd`

```ts
// Match any of several patterns
Match.whenOr({ _tag: "A" }, { _tag: "B" }, (_) => "A or B")

// Match all patterns simultaneously (intersection)
Match.whenAnd({ age: (n) => n >= 18 }, { role: "admin" }, (_) => "adult admin")
```

### Completion options

| Finalizer | Behavior |
|-----------|---------|
| `Match.exhaustive` | TypeScript error if remaining cases exist |
| `Match.orElse(f)` | Fallback for unmatched cases |
| `Match.orElseAbsurd` | Throws if any case is unmatched (runtime) |
| `Match.option` | Wraps result in `Option` — `None` if unmatched |
| `Match.either` | Wraps result in `Either` — `Left(unmatched)` if unmatched |

### Built-in predicates for `Match.when`

```ts
Match.string    // Refinement<unknown, string>
Match.number    // Refinement<unknown, number>
Match.boolean   // Refinement<unknown, boolean>
Match.bigint    // Refinement<unknown, bigint>
Match.symbol    // Refinement<unknown, symbol>
Match.date      // Refinement<unknown, Date>
Match.null      // Refinement<unknown, null>
Match.undefined // Refinement<unknown, undefined>
Match.any       // SafeRefinement<unknown, any>
Match.defined   // Refinement<A, A & {}>
Match.is("a", 1, true)  // matches specific literals
Match.nonEmptyString    // non-empty string
Match.instanceOf(MyClass)
```

### `Match.tags` / `Match.tagsExhaustive` — shorthand for `_tag` unions

```ts
// Non-exhaustive — same as chaining Match.tag calls
const handle = Match.type<Event>().pipe(
  Match.tags({
    Login:  (e) => `login: ${e.userId}`,
    Logout: (e) => `logout: ${e.userId}`,
  }),
  Match.orElse((_) => "unknown event")
)

// Exhaustive — no Match.exhaustive needed at end
const handleAll = Match.type<Event>().pipe(
  Match.tagsExhaustive({
    Login:  (e) => `login: ${e.userId}`,
    Logout: (e) => `logout: ${e.userId}`,
    Error:  (e) => `error: ${e.message}`,
  })
)
```

---

## Persistent Collections

### `Chunk<A>`

An immutable, O(1) concat sequence. Backed by a tree of arrays; `toArray()` / iteration is efficient. Use when you need persistent append or prepend semantics.

```ts
import { Chunk } from "effect"

const c1 = Chunk.make(1, 2, 3)           // Chunk<number>
const c2 = Chunk.of(4)
const c3 = Chunk.append(c1, 4)          // Chunk(1,2,3,4) — O(1)
const c4 = Chunk.prepend(c1, 0)         // Chunk(0,1,2,3)
const c5 = Chunk.appendAll(c1, c2)      // concat — O(1)

Chunk.size(c1)           // 3
Chunk.get(c1, 0)         // Option<number>
Chunk.unsafeGet(c1, 0)   // number — throws if OOB
Chunk.toArray(c1)        // number[]
Chunk.isEmpty(Chunk.empty())  // true

// Transformation
Chunk.map(c1, (n) => n * 2)
Chunk.filter(c1, (n) => n > 1)
Chunk.flatMap(c1, (n) => Chunk.make(n, n * 2))
Chunk.take(c1, 2)        // first 2 elements
Chunk.drop(c1, 1)        // drop first 1
```

**When to use vs native array**: Use `Chunk` when you accumulate many appends (e.g., collecting streaming results), since `Chunk.append` is O(1) vs array O(n). Convert to array at the boundary with `Chunk.toArray`.

### `HashMap<Key, Value>`

An immutable, structurally equal hash map that uses Effect's `Equal`/`Hash` protocol for keys.

```ts
import { HashMap } from "effect"

const empty = HashMap.empty<string, number>()
const m1 = HashMap.set(empty, "a", 1)
const m2 = HashMap.set(m1, "b", 2)
const m3 = HashMap.remove(m2, "a")

HashMap.get(m2, "a")         // Option<number>
HashMap.getOrElse(m2, "z", () => 0)  // number
HashMap.has(m2, "b")         // true
HashMap.size(m2)             // 2

// Iteration
HashMap.keys(m2)             // Iterable<string>
HashMap.values(m2)           // Iterable<number>
HashMap.entries(m2)          // Iterable<[string, number]>
HashMap.toEntries(m2)        // Array<[string, number]>

// Transformation
HashMap.map(m2, (v, k) => v * 2)
HashMap.filter(m2, (v) => v > 1)
HashMap.mapKeys(m2, (k) => k.toUpperCase())
HashMap.union(m1, m2)        // merge — right wins on collision
```

**Key requirement**: Keys must implement `Equal.Equal`. `Data.struct` / `Data.Class` instances work. Plain objects do NOT.

### `HashSet<Value>`

An immutable, structurally equal set.

```ts
import { HashSet } from "effect"

const s1 = HashSet.make(1, 2, 3)
const s2 = HashSet.add(s1, 4)
const s3 = HashSet.remove(s1, 2)

HashSet.has(s1, 3)    // true
HashSet.size(s1)      // 3

HashSet.union(s1, HashSet.make(3, 4, 5))       // {1,2,3,4,5}
HashSet.intersection(s1, HashSet.make(2, 3, 4)) // {2,3}
HashSet.difference(s1, HashSet.make(2))          // {1,3}
HashSet.isSubset(HashSet.make(1, 2), s1)         // true

HashSet.map(s1, (n) => n * 2)
HashSet.filter(s1, (n) => n > 1)
```

### Choosing the right collection

| Need | Use |
|------|-----|
| Mutable array ops | Native `Array` |
| Persistent efficient append/prepend | `Chunk` |
| Key/value lookup by structural equality | `HashMap` |
| Unique membership by structural equality | `HashSet` |
| Sorted by `Order` | `SortedMap` / `SortedSet` |
| Singly-linked persistent list | `List` |

---

## Functional Data Utilities

### `Array` (effect/Array)

Rich functional array module. All functions are data-last for `pipe`.

```ts
import { Array } from "effect"

Array.map([1, 2, 3], (n) => n * 2)
Array.filter([1, 2, 3], (n) => n > 1)
Array.flatMap([1, 2], (n) => [n, n * 2])
Array.partition([1, 2, 3, 4], (n) => n % 2 === 0)  // [odds, evens]
Array.groupBy([1, 2, 3, 4], (n) => n % 2 === 0 ? "even" : "odd")
Array.sortBy([3, 1, 2], Order.number)
Array.dedupeWith([1, 1, 2, 2], Equal.equals)
Array.findFirst([1, 2, 3], (n) => n > 1)  // Option<number>
Array.head([1, 2, 3])                      // Option<1>
Array.tail([1, 2, 3])                      // Option<[2, 3]>
Array.isNonEmptyArray([1])                 // type guard
Array.ensure(x)                            // wraps non-array in array
```

### `Record` (effect/Record)

```ts
import { Record } from "effect"

const rec = { a: 1, b: 2, c: 3 }
Record.map(rec, (v) => v * 2)          // { a: 2, b: 4, c: 6 }
Record.filter(rec, (v) => v > 1)       // { b: 2, c: 3 }
Record.keys(rec)                        // ["a", "b", "c"]
Record.values(rec)                      // [1, 2, 3]
Record.has(rec, "a")                   // true
Record.get(rec, "a")                   // Option<number>
Record.mapKeys(rec, (k) => k.toUpperCase())
Record.fromEntries([["a", 1], ["b", 2]])  // { a: 1, b: 2 }
```

### `Struct` (effect/Struct)

```ts
import { Struct } from "effect"

const user = { id: 1, name: "Alice", role: "admin" }
Struct.pick(user, "id", "name")    // { id: 1, name: "Alice" }
Struct.omit(user, "role")          // { id: 1, name: "Alice" }
Struct.get("name")(user)           // "Alice"
Struct.evolve(user, { name: (n) => n.toUpperCase() })
```

### `Tuple` (effect/Tuple)

```ts
import { Tuple } from "effect"

const t = Tuple.make(1, "hello")          // readonly [1, "hello"]
Tuple.getFirst(t)                          // 1
Tuple.getSecond(t)                         // "hello"
Tuple.mapFirst(t, (n) => n + 1)
Tuple.mapSecond(t, (s) => s.length)
Tuple.swap(t)                              // ["hello", 1]
```

### `Order` (effect/Order)

`Order<A>` is `(a: A, b: A) => -1 | 0 | 1`. Used for sorting and comparison.

```ts
import { Order } from "effect"

Order.number        // Order<number>
Order.string        // Order<string>
Order.boolean       // Order<boolean>
Order.bigint        // Order<bigint>
Order.Date          // Order<Date>

// Derive orders
Order.reverse(Order.number)                 // descending
Order.mapInput(Order.number, (s: string) => s.length)
Order.combine(Order.string, Order.number)  // lexicographic pair
Order.combineAll([o1, o2, o3])

// Use for comparison
Order.lessThan(Order.number)(1, 2)         // true
Order.greaterThanOrEqualTo(Order.string)("b", "a")  // true
Order.clamp(Order.number)({ minimum: 0, maximum: 100 })(150)  // 100
Order.between(Order.number)({ minimum: 0, maximum: 100 })(50) // true
```

### `Equivalence` (effect/Equivalence)

`Equivalence<A>` is `(a: A, b: A) => boolean`.

```ts
import { Equivalence } from "effect"

Equivalence.string           // string equality
Equivalence.number           // number equality
Equivalence.boolean          // boolean equality
Equivalence.Date             // Date equality by time

// Derive
Equivalence.mapInput(Equivalence.string, (u: { name: string }) => u.name)
Equivalence.combine(e1, e2)  // both must agree
Equivalence.make((a, b) => a.id === b.id)  // custom
```

### `Predicate` (effect/Predicate)

```ts
import { Predicate } from "effect"

Predicate.isString(x)
Predicate.isNumber(x)
Predicate.isBoolean(x)
Predicate.isNull(x)
Predicate.isUndefined(x)
Predicate.isNullable(x)       // null | undefined
Predicate.isNotNull(x)
Predicate.isNotUndefined(x)
Predicate.isRecord(x)         // { [string|symbol]: unknown }
Predicate.isFunction(x)
Predicate.isDate(x)
Predicate.isBigInt(x)
Predicate.isTagged("MyTag")(x)  // x._tag === "MyTag"

// Combinators
Predicate.not(isString)
Predicate.and(isNumber, (n) => n > 0)
Predicate.or(isNull, isUndefined)
```

---

## Function Utilities

### `pipe`

Passes a value through a sequence of single-argument functions:

```ts
import { pipe } from "effect"

const result = pipe(
  [1, 2, 3, 4],
  Array.filter((n) => n % 2 === 0),
  Array.map((n) => n * 10),
)
// [20, 40]
```

❌ Don't: `Array.map(Array.filter([1,2,3,4], (n) => n%2===0), (n) => n*10)` — hard to read

✅ Do: use `pipe` to read transformations top-to-bottom

### `flow`

Composes functions into a new function (point-free):

```ts
import { flow } from "effect"

const processItems = flow(
  Array.filter<number>((n) => n % 2 === 0),
  Array.map((n) => n * 10),
)

processItems([1, 2, 3, 4])  // [20, 40]
```

`flow(f, g, h)` is equivalent to `(x) => pipe(x, f, g, h)`.

### `identity` / `constant`

```ts
import { identity, constant } from "effect/Function"

identity(42)          // 42  — useful as a no-op transform
constant("hello")()   // "hello" — returns same value every call
```

### `dual`

Makes a function work both data-first and data-last (enabling `pipe`):

```ts
import { dual } from "effect/Function"

const add = dual<
  (b: number) => (a: number) => number,
  (a: number, b: number) => number
>(2, (a, b) => a + b)

add(1, 2)             // data-first: 3
pipe(1, add(2))       // data-last: 3
```

Effect's own data-last style is why all collection functions work in `pipe`:
`Array.map(arr, fn)` ≡ `pipe(arr, Array.map(fn))`.

---

## Patterns

### Exhaustive tagged union handling

```ts
import { Match, Data } from "effect"

type Shape = Data.TaggedEnum<{
  Circle:    { radius: number }
  Rectangle: { width: number; height: number }
  Triangle:  { base: number; height: number }
}>
const { Circle, Rectangle, Triangle } = Data.taggedEnum<Shape>()

const area = Match.type<Shape>().pipe(
  Match.tag("Circle",    (s) => Math.PI * s.radius ** 2),
  Match.tag("Rectangle", (s) => s.width * s.height),
  Match.tag("Triangle",  (s) => (s.base * s.height) / 2),
  Match.exhaustive
)
```

### Building a map from an array

```ts
pipe(
  users,
  Array.groupBy((u) => u.role),  // Record<string, User[]>
)

// Or as a HashMap keyed by Data.struct:
pipe(
  users,
  Array.reduce(
    HashMap.empty<Data.Data<{ id: number }>, User>(),
    (map, u) => HashMap.set(map, Data.struct({ id: u.id }), u)
  )
)
```

### Structural equality in tests

```ts
import { Equal, Data } from "effect"
import * as assert from "node:assert"

const result = processUser({ id: 1, name: "Alice" })
const expected = Data.struct({ id: 1, name: "Alice", role: "admin" })
assert.ok(Equal.equals(result, expected))
```

---

## See also

- `Option` source: `/packages/effect/src/Option.ts`
- `Either` source: `/packages/effect/src/Either.ts`
- `Data` source: `/packages/effect/src/Data.ts`
- `Match` source: `/packages/effect/src/Match.ts`
- `Brand` source: `/packages/effect/src/Brand.ts`
- `Chunk` source: `/packages/effect/src/Chunk.ts`
- `HashMap` source: `/packages/effect/src/HashMap.ts`
- `HashSet` source: `/packages/effect/src/HashSet.ts`
- `Function` source: `/packages/effect/src/Function.ts`
- Effect docs: https://effect.website/docs/data-types/option
- Effect docs: https://effect.website/docs/data-types/either
- Effect docs: https://effect.website/docs/pattern-matching
