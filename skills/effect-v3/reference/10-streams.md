# Streams

**When you reach for this:** You need to process a sequence of values that may be infinite, arrive asynchronously, require resource management around acquisition/release, need back-pressure between producer and consumer, or cannot be safely collected into memory all at once. Use `Effect<Chunk<A>>` when the entire collection fits comfortably in memory and the source is finite. Use `Stream<A, E, R>` when any of those assumptions break — infinite sources, paginated APIs, file reads, queue drains, WebSocket feeds, or multi-stage pipelines with bounded concurrency.

---

## Contents

- [The type](#the-type)
- [Constructors](#constructors)
- [Transformations](#transformations)
- [Error handling](#error-handling)
- [Resources and scoped streams](#resources-and-scoped-streams)
- [Running streams](#running-streams)
- [`Sink<A, In, L, E, R>`](#sinka-in-l-e-r)
- [`Channel` — the low-level primitive](#channel-the-low-level-primitive)
- [End-to-end example: read → transform → batch → write](#end-to-end-example-read-transform-batch-write)
- [Common pitfalls](#common-pitfalls)
- [See also](#see-also)


## The type

```ts
import { Stream, Sink, Effect, Chunk } from "effect"

// Stream<A, E, R>
//   A – element type emitted
//   E – typed failure (never = infallible)
//   R – requirements (services from context)
```

`Stream` is a purely functional, **pull-based**, back-pressured, possibly-infinite sequence. It does not buffer unboundedly — downstream pulls at its own pace, and upstream only advances when pulled. Internally, elements are batched into `Chunk<A>` to amortise the cost of effect evaluation; this is an implementation detail you rarely see unless you use the chunk-level operators.

`Stream` forms a monad on `A` (via `flatMap`), mirrors `Effect`'s error model on `E`, and propagates `R` requirements the same way `Effect` does.

---

## Constructors

### Pure / synchronous

```ts
// One or more literal values
const s1 = Stream.make(1, 2, 3)                    // Stream<number>

// From any Iterable (lazy — not consumed until pulled)
const s2 = Stream.fromIterable([1, 2, 3])           // Stream<number>

// Empty stream
const s3 = Stream.empty                             // Stream<never>

// Always-fail stream
const s4 = Stream.fail(new Error("boom"))           // Stream<never, Error>

// Infinite range [min, max) — chunkSize optional
const s5 = Stream.range(0, 100)                     // Stream<number>

// Infinite iteration: 0, 1, 2, ...
const s6 = Stream.iterate(0, (n) => n + 1)          // Stream<number>

// Unfold: emit values as long as f returns Some([value, nextState])
const s7 = Stream.unfold(0, (n) =>
  n < 5 ? Option.some([n, n + 1] as const) : Option.none()
)
```

### From effects

```ts
import { Effect, Option, Queue, PubSub } from "effect"

// Lift a single Effect into a one-element stream
const fromE = Stream.fromEffect(Effect.succeed(42))           // Stream<number>

// Lift a scoped resource — finalizer runs when stream ends
const fromScoped = Stream.scoped(
  Effect.acquireRelease(openResource, closeResource)
)

// Repeat an effect forever (infinite stream of poll results)
const polling = Stream.repeatEffect(fetchLatestReading)       // Stream<Reading>

// Repeat until effect fails with None (signals end-of-stream)
const drainIterator = <A>(it: Iterator<A>) =>
  Stream.repeatEffectOption(
    Effect.sync(() => it.next()).pipe(
      Effect.andThen((res) =>
        res.done
          ? Effect.fail(Option.none())
          : Effect.succeed(res.value)
      )
    )
  )
```

### Paginated sources

```ts
// paginate: emit one value per page, Option<S> = next cursor (None = done)
const pages = Stream.paginate(
  "https://api.example.com/items?page=1",
  (url) => [fetchPage(url), nextUrl(url)]    // [A, Option<nextState>]
)

// paginateEffect: async cursor-based pagination
const items = Stream.paginateEffect(
  { cursor: null as string | null },
  ({ cursor }) =>
    Effect.gen(function* () {
      const page = yield* fetchItems(cursor)
      return [page.items, page.nextCursor ? Option.some({ cursor: page.nextCursor }) : Option.none()] as const
    })
)
// ❌ don't: paginate<S, A>(s, f) — the non-effect version only works for pure cursors
// ✅ do: paginateEffect for any async API call
```

### From concurrency primitives

```ts
// Drain a Queue (stream ends when queue is shutdown)
const fromQ   = Stream.fromQueue(queue)             // Stream<A>

// Subscribe to a PubSub (each subscriber gets all messages from subscription point)
const fromPS  = Stream.fromPubSub(pubsub)           // Stream<A>

// Back-interop: wrap an async push source
const fromPush = Stream.asyncPush<string>((emit) =>
  Effect.acquireRelease(
    Effect.sync(() => setInterval(() => emit.single("tick"), 100)),
    (handle) => Effect.sync(() => clearInterval(handle))
  ),
  { bufferSize: 16, strategy: "dropping" }
)

// asyncEffect — lower-level; emit via Emit<R,E,A,void>; bufferSize controls back-pressure
const fromAsync = Stream.asyncEffect<number>((emit) =>
  Effect.sync(() => {
    const id = setInterval(() => emit.single(Date.now()), 1000)
    return () => Effect.sync(() => clearInterval(id))
  })
)
```

### Timed / scheduled sources

```ts
// Emit void on an interval
const ticks = Stream.tick("1 second")              // Stream<void>

// Emit schedule output at each recurrence
const scheduled = Stream.fromSchedule(Schedule.spaced("500 millis"))

// Repeat a stream on a schedule (re-runs stream each time schedule fires)
const repeated = Stream.repeat(Stream.make(1, 2, 3), Schedule.recurs(4))
```

### Channel interop

```ts
// Wrap a raw Channel as a Stream (low-level escape hatch)
const fromChan = Stream.fromChannel(myChannel)
// Convert back
const chan = Stream.toChannel(myStream)
```

---

## Transformations

### Element-level mapping

```ts
// Pure map
stream.pipe(Stream.map((n) => n * 2))

// Effectful map — sequential by default
stream.pipe(Stream.mapEffect((n) => Effect.succeed(n * 2)))

// Bounded concurrency — up to 4 effects in flight, ordered
stream.pipe(Stream.mapEffect(callApi, { concurrency: 4 }))

// Unordered bounded concurrency — results emitted as soon as ready
stream.pipe(Stream.mapEffect(callApi, { concurrency: 8, unordered: true }))

// Keyed concurrency — one in-flight per key, new value for same key cancels previous
stream.pipe(Stream.mapEffect(callApi, { key: (item) => item.id }))

// mapConcat — map each element to an Iterable and flatten
stream.pipe(Stream.mapConcat((line) => line.split(",")))

// Stateful map: carry state without flattening
stream.pipe(Stream.mapAccum(0, (count, a) => [count + 1, { index: count, value: a }] as const))
```

### Filtering

```ts
stream.pipe(Stream.filter((n) => n % 2 === 0))
stream.pipe(Stream.filterMap((n) => n > 0 ? Option.some(n) : Option.none()))
stream.pipe(Stream.filterEffect((n) => checkAsync(n)))
```

### Taking / dropping

```ts
stream.pipe(Stream.take(5))
stream.pipe(Stream.takeWhile((n) => n < 100))
stream.pipe(Stream.takeUntil((n) => n === 0))   // inclusive — emits the matching element
stream.pipe(Stream.drop(3))
stream.pipe(Stream.dropWhile((s) => s === ""))
```

### Scanning / accumulation

```ts
// scan: emit all intermediate states (like reduce but keeps each step)
stream.pipe(Stream.scan(0, (acc, n) => acc + n))          // running total

// mapAccum: stateful map where state is threaded but only mapped value is emitted
stream.pipe(Stream.mapAccum([], (acc, a) => [[...acc, a], acc.length]))
```

### FlatMap / concatentation

```ts
// flatMap: sequential (strict ordering)
stream.pipe(Stream.flatMap((path) => Stream.fromEffect(readFile(path))))

// flatMap with concurrency (merge): up to N inner streams running in parallel
stream.pipe(Stream.flatMap(expand, { concurrency: 4 }))

// flatMap with switch: cancel in-flight inner stream when a new upstream value arrives
stream.pipe(Stream.flatMap(search, { switch: true }))

// flatten: Stream<Stream<A>> → Stream<A>
streamOfStreams.pipe(Stream.flatten({ concurrency: 4 }))
```

### Merging streams

```ts
// Merge two streams non-deterministically (both sides run in parallel)
Stream.merge(left, right)                          // ends when both end
Stream.merge(left, right, { haltStrategy: "left" }) // ends when left ends

// Merge N streams with bounded concurrency
Stream.mergeAll([ s1, s2, s3 ], { concurrency: 2 })

// Merge with tagged discriminator (v3.8.5+)
Stream.mergeWithTag({ users: userStream, orders: orderStream })
// emits { _tag: "users", ... } | { _tag: "orders", ... }
```

### Zipping

```ts
// zip: pair elements by position; ends when shorter stream ends
Stream.zip(left, right)                            // Stream<[A, B]>
Stream.zipWith(left, right, (a, b) => a + b)       // Stream<C>

// zipLatest: whenever either side emits, pair with the OTHER side's latest value
Stream.zipLatest(prices, quantities)               // continuous reactive join

// zipLatestAll: N-ary version
Stream.zipLatestAll(s1, s2, s3)
```

### Grouping / batching

```ts
// Fixed-size batches: Stream<Chunk<A>>
stream.pipe(Stream.grouped(100))

// Time-or-size batches
stream.pipe(Stream.groupedWithin(100, "1 second"))

// Partition into two streams by predicate (scoped — both must be consumed)
const [odds, evens] = yield* Effect.scoped(
  stream.pipe(Stream.partition((n) => n % 2 === 0))
)

// Group by computed key → GroupBy<K, V, E, R>
stream.pipe(
  Stream.groupByKey((item) => item.category),
  GroupBy.evaluate((category, substream) =>
    substream.pipe(
      Stream.take(10),
      Stream.map((item) => [category, item] as const)
    )
  )
)

// groupBy with effectful key derivation
stream.pipe(
  Stream.groupBy((item) => Effect.succeed([item.tenantId, item] as const)),
  GroupBy.evaluate((tenantId, substream) =>
    substream.pipe(Stream.runFold(0, (acc) => acc + 1), Stream.fromEffect)
  )
)
```

### Rechunking / buffering

```ts
// Re-segment into chunks of exactly n (useful before a batched write)
stream.pipe(Stream.rechunk(50))

// Decouple producer and consumer with a bounded async queue
stream.pipe(Stream.buffer({ capacity: 256, strategy: "suspend" }))
//   strategy "suspend"  — back-pressure (producer waits when buffer full)
//   strategy "dropping" — overflow elements are dropped silently
//   strategy "sliding"  — oldest elements are evicted to make room
stream.pipe(Stream.buffer({ capacity: "unbounded" }))   // no back-pressure
```

### Rate limiting

```ts
// Token-bucket throttle: shape (delay) or enforce (drop)
stream.pipe(
  Stream.throttle({
    cost: (chunk) => chunk.length,    // cost per chunk
    units: 1000,                      // tokens per window
    duration: "1 second",
    burst: 200,                       // allow bursting up to 1200
    strategy: "shape",                // "enforce" to drop instead
  })
)

// Debounce: emit only after a quiet period
stream.pipe(Stream.debounce("300 millis"))

// Schedule each element according to a schedule
stream.pipe(Stream.schedule(Schedule.spaced("100 millis")))
```

### Fan-out / multicast

```ts
// broadcast: split into N identical streams; back-pressures producer if any consumer lags
const [s1, s2] = yield* Effect.scoped(
  Stream.broadcast(stream, 2, { capacity: 16 })
)

// share: multicast with lazy start; upstream starts on first subscriber, stops on last
const shared = yield* Effect.scoped(
  Stream.share(stream, { capacity: 64, idleTimeToLive: "5 seconds" })
)

// distributedWith: route each element to specific downstream queues by predicate
const [lowQ, highQ] = yield* Effect.scoped(
  stream.pipe(
    Stream.distributedWith({
      size: 2,
      maximumLag: 100,
      decide: (n) => Effect.succeed((i: number) => i === (n < 50 ? 0 : 1)),
    })
  )
)
```

### Side effects (tap)

```ts
stream.pipe(Stream.tap((n) => Effect.log(`processing ${n}`)))
stream.pipe(Stream.tapBoth({
  onFailure: (e) => Effect.log(`error: ${e}`),
  onSuccess: (a) => Effect.log(`ok: ${a}`),
}))
```

---

## Error handling

```ts
// Recover from typed errors with another stream
stream.pipe(Stream.catchAll((e) => Stream.empty))

// Recover from all failures including defects / interruption
stream.pipe(Stream.catchAllCause((cause) => Stream.failCause(cause)))

// Pattern-match on error _tag
stream.pipe(Stream.catchTag("NotFound", (_e) => Stream.empty))
stream.pipe(Stream.catchTags({
  NotFound: (_e) => Stream.empty,
  Timeout:  (_e) => fallbackStream,
}))

// Fallback to another stream on any failure
stream.pipe(Stream.orElse(() => fallbackStream))

// Retry on failure using a Schedule
stream.pipe(Stream.retry(Schedule.exponential("100 millis").pipe(Schedule.recurs(5))))

// Timeout: end the stream if no element arrives within the window
stream.pipe(Stream.timeout("5 seconds"))

// Fail with a specific error on timeout
stream.pipe(Stream.timeoutFail(() => new TimeoutError(), "5 seconds"))

// Switch to a different stream on timeout
stream.pipe(Stream.timeoutTo("5 seconds", fallbackStream))
```

---

## Resources and scoped streams

```ts
// acquireRelease: emit the resource, finalize when stream ends
const managed = Stream.acquireRelease(
  openFile("data.csv"),
  (file) => file.close
).pipe(
  Stream.flatMap((file) => readLines(file))
)

// scoped: lift a scoped Effect into a single-element stream
const oneShot = Stream.scoped(
  Effect.acquireRelease(connect(), disconnect)
)

// unwrapScoped: run a scoped Effect that returns a Stream, then stream it
const dynamic = Stream.unwrapScoped(
  Effect.gen(function* () {
    const conn = yield* Effect.acquireRelease(connect(), disconnect)
    return readFrom(conn)
  })
)
```

---

## Running streams

All runners return `Effect<..., E, R>` — they are lazy until run.

```ts
// Collect all elements into a Chunk
const all: Chunk.Chunk<number> = yield* Stream.runCollect(stream)

// Consume each element with an effectful callback
yield* Stream.runForEach(stream, (n) => Effect.log(String(n)))

// Run for effects only, discard values
yield* Stream.runDrain(stream)

// Reduce to a single value
const sum: number = yield* Stream.runFold(stream, 0, (acc, n) => acc + n)

// First element (Option<A>)
const head: Option.Option<number> = yield* Stream.runHead(stream)

// Last element (Option<A>)
const last: Option.Option<number> = yield* Stream.runLast(stream)

// Run into a custom Sink
const result = yield* Stream.run(stream, Sink.sum)

// Convert to Web ReadableStream (no R requirement)
const readable: ReadableStream<number> = Stream.toReadableStream(stream)

// Convert to Web ReadableStream while capturing requirements
const readableE: Effect.Effect<ReadableStream<number>> =
  Stream.toReadableStreamEffect(stream)

// Convert to AsyncIterable (no R requirement)
const asyncIter: AsyncIterable<number> = Stream.toAsyncIterable(stream)
```

---

## `Sink<A, In, L, E, R>`

A `Sink` consumes elements of type `In`, may leave unconsumed elements of type `L`, fails with `E`, and yields a result of type `A`.

```
Sink<A, In, L, E, R>
  A   – result value
  In  – input element type
  L   – leftover (unconsumed input passed downstream)
  E   – error
  R   – requirements
```

### Built-in sinks

```ts
import { Sink } from "effect"

Sink.collectAll<In>()                    // Sink<Chunk<In>, In>
Sink.head<In>()                          // Sink<Option<In>, In, In>
Sink.last<In>()                          // Sink<Option<In>, In, In>
Sink.count                               // Sink<number, unknown>
Sink.sum                                 // Sink<number, number>
Sink.drain                               // Sink<void, unknown>

// Fold with early termination (contFn returns false to stop)
Sink.fold<S, In>(
  initialState,
  (s) => s.count < 100,              // continue?
  (s, input) => ({ ...s, count: s.count + 1 })
)

// Effectful fold
Sink.foldEffect<S, In, E, R>(
  initialState,
  (s) => s < 1000,
  (s, input) => writeRow(s, input).pipe(Effect.as(s + 1))
)

// For-each (run an effect per element)
Sink.forEach<In, X, E, R>((item) => persist(item))

// Collect up to N elements
Sink.collectAllN<In>(50)               // Sink<Chunk<In>, In, In>

// Weighted fold (batch by cost, e.g. bytes)
Sink.foldWeighted<S, In>({
  initial: [],
  maxCost: 65536,
  cost: (_, item) => Buffer.byteLength(JSON.stringify(item)),
  body: (batch, item) => [...batch, item],
})
```

### Transforming sinks

```ts
// Map output
Sink.map(sink, (a) => a * 2)

// Map effectfully
Sink.mapEffect(sink, (a) => Effect.succeed(a * 2))

// Contramap input
Sink.mapInput(sink, (s: string) => s.length)

// Race two sinks — whichever finishes first wins
Sink.race(Sink.head(), Sink.collectAllN(10))
```

### Connecting sinks to streams

```ts
// Generic run
const result = yield* Stream.run(myStream, Sink.collectAll())

// transduce: apply a sink repeatedly, re-emitting its result as a new stream
// Useful for implementing custom windowing
const batched = stream.pipe(
  Stream.transduce(Sink.collectAllN(25))
)
```

---

## `Channel` — the low-level primitive

```ts
import { Channel } from "effect"

// Channel<OutElem, InElem, OutErr, InErr, OutDone, InDone, Env>
```

Both `Stream` and `Sink` are built on `Channel`. A channel is a bidirectional coroutine: it reads upstream `InElem` values and writes downstream `OutElem` values, terminating with `OutDone`.

**When to drop to Channel:**
- Writing a new `Stream` or `Sink` combinator that cannot be expressed with existing operators.
- Bidirectional streaming protocols (e.g., WebSocket request/response multiplexing).
- Custom chunking strategies that require direct access to the underlying pull loop.
- Building a transducer that needs to both consume and produce with leftover tracking.

**Key Channel operations:**
```ts
Channel.pipeTo(upstream, downstream)   // compose two channels
Channel.read<In>()                     // pull one element
Channel.write(value)                   // emit one element
Channel.flatMap(chan, (done) => next)   // sequence on terminal value
Channel.mergeWith(left, right, opts)   // concurrent merge

// Convert between Channel ↔ Stream / Sink
Stream.fromChannel(channel)
Sink.fromChannel(channel)
Stream.toChannel(stream)
Sink.toChannel(sink)
```

In practice you will rarely need `Channel` directly — `Stream.flatMap`, `Stream.mapEffect`, `Sink.foldEffect`, and `Stream.transduce` cover the vast majority of real pipelines.

---

## End-to-end example: read → transform → batch → write

This pattern shows a realistic pipeline: read from a queue with back-pressure, enrich items concurrently (bounded), batch by time-or-count, and write each batch with a managed connection.

```ts
import { Effect, Queue, Sink, Stream, Schedule } from "effect"
import { NodeRuntime } from "@effect/platform-node"

interface RawEvent { id: string; payload: string }
interface EnrichedEvent { id: string; payload: string; metadata: Record<string, string> }

const program = Effect.gen(function* () {
  const queue = yield* Queue.bounded<RawEvent>(1024)

  // Simulate a producer filling the queue (in reality, this would be your event source)
  yield* Effect.forkScoped(
    Effect.forever(
      Effect.gen(function* () {
        yield* Queue.offer(queue, { id: crypto.randomUUID(), payload: "data" })
        yield* Effect.sleep("10 millis")
      })
    )
  )

  yield* Stream.fromQueue(queue).pipe(
    // --- enrichment: up to 8 concurrent API calls, results ordered ---
    Stream.mapEffect(
      (event): Effect.Effect<EnrichedEvent> =>
        Effect.gen(function* () {
          const meta = yield* fetchMetadata(event.id)
          return { ...event, metadata: meta }
        }),
      { concurrency: 8 }
    ),

    // --- batch: up to 200 items OR 500 ms, whichever comes first ---
    Stream.groupedWithin(200, "500 millis"),

    // --- write each batch using a managed DB connection ---
    Stream.mapEffect(
      (batch) =>
        Effect.gen(function* () {
          const db = yield* acquireDb()
          yield* writeBatch(db, batch)
          yield* releaseDb(db)
        }),
      { concurrency: 1 }   // serialise writes — one batch at a time
    ),

    // --- discard the void results and run for effects ---
    Stream.runDrain
  )
})

// Stubs to make the example typecheck
declare function fetchMetadata(id: string): Effect.Effect<Record<string, string>>
declare function acquireDb(): Effect.Effect<unknown>
declare function releaseDb(db: unknown): Effect.Effect<void>
declare function writeBatch(db: unknown, batch: import("effect").Chunk.Chunk<EnrichedEvent>): Effect.Effect<void>

NodeRuntime.runMain(Effect.scoped(program))
```

**What makes this back-pressured end-to-end:**
1. `Stream.fromQueue` only pulls from the queue when the downstream is ready.
2. `mapEffect({ concurrency: 8 })` limits in-flight enrichments; if downstream is busy, the queue backs up and the upstream producer hits `Queue.offer` back-pressure.
3. `groupedWithin` holds elements until either the count or time limit is met.
4. `mapEffect({ concurrency: 1 })` on writes means at most one active DB write — any excess batches wait in the stream buffer.

---

## Common pitfalls

```ts
// ❌ Collecting an infinite stream
yield* Stream.runCollect(Stream.iterate(0, (n) => n + 1))   // hangs forever

// ✅ Bound it first
yield* Stream.runCollect(Stream.range(0, 1000))

// ❌ mapEffect without bounding concurrency on an expensive operation
stream.pipe(Stream.mapEffect(callExpensiveApi))              // sequential — slow

// ✅ Set concurrency explicitly
stream.pipe(Stream.mapEffect(callExpensiveApi, { concurrency: 16 }))

// ❌ Forgetting to consume both sides of partition (causes deadlock)
const [a, b] = yield* Effect.scoped(Stream.partition(stream, pred))
yield* Stream.runDrain(a)       // b is never consumed → deadlock

// ✅ Consume both in parallel
yield* Effect.all([Stream.runDrain(a), Stream.runDrain(b)], { concurrency: 2 })

// ❌ Using Stream.buffer without a strategy — default "suspend" will back-pressure,
//    which is usually what you want, but "unbounded" can cause OOM on fast producers
stream.pipe(Stream.buffer({ capacity: "unbounded" }))        // no back-pressure!

// ✅ Prefer a finite capacity with suspend
stream.pipe(Stream.buffer({ capacity: 256, strategy: "suspend" }))
```

---

## See also

- `Effect.gen` and `Effect.scoped` — the runner context for streams
- `Queue` and `PubSub` — concurrency primitives that feed streams
- `Schedule` — controls retry, throttle, repeat, and groupedWithin timing
- `Chunk` — the internal array-like batch type; use `Chunk.toArray` / `Chunk.fromIterable` at boundaries
- `GroupBy` — the `evaluate` / `filter` / `first` API for group-by pipelines
- Effect docs "Streaming" section: https://effect.website/docs/stream/introduction
- `packages/effect/src/Stream.ts` (branch `v3`) — authoritative source for every signature
- `packages/effect/src/Sink.ts` — sink constructors and combinators
- `packages/effect/src/Channel.ts` — low-level primitive; useful when writing new operators
