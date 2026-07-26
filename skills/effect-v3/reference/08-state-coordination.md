# 08 — State & Coordination

When you reach for this: you need shared mutable state across fibers (`Ref`), effectful atomic updates (`SynchronizedRef`), fiber-local values (`FiberRef`), a one-shot async variable (`Deferred`), a typed producer/consumer channel (`Queue`), fan-out pub/sub (`PubSub`), bounded concurrency (`Semaphore`), a start-gate (`Latch`), a bounded actor inbox (`Mailbox`), or multi-variable invariant protection without locks (`STM`/`TRef`).

---

## Contents

- [`Ref<A>` — shared mutable state](#refa-shared-mutable-state)
- [`SynchronizedRef<A>` — effectful atomic updates](#synchronizedrefa-effectful-atomic-updates)
- [`SubscriptionRef<A>` — a `Ref` you can subscribe to](#subscriptionrefa-a-ref-you-can-subscribe-to)
- [`FiberRef<A>` — fiber-local state](#fiberrefa-fiber-local-state)
- [`Deferred<A, E>` — one-shot async variable](#deferreda-e-one-shot-async-variable)
- [`Queue<A>` — typed async channel](#queuea-typed-async-channel)
- [`PubSub<A>` — fan-out pub/sub](#pubsuba-fan-out-pubsub)
- [`Effect.makeSemaphore` — concurrency control](#effectmakesemaphore-concurrency-control)
- [`Effect.Latch` — start gate / synchronization barrier](#effectlatch-start-gate-synchronization-barrier)
- [`Mailbox<A, E>` — bounded actor inbox (experimental)](#mailboxa-e-bounded-actor-inbox-experimental)
- [STM — Software Transactional Memory](#stm-software-transactional-memory)
- [Quick selection guide](#quick-selection-guide)
- [See also](#see-also)


## `Ref<A>` — shared mutable state

A `Ref` is a concurrent, composable mutable cell. **All operations are atomic and return `Effect`s.** `Ref` itself is also a `Readable<A>` and an `Effect<A>` (yields its value when yielded in `gen`).

```ts
import { Effect, Ref } from "effect"

const program = Effect.gen(function* () {
  const counter = yield* Ref.make(0)

  // get / set
  const n = yield* Ref.get(counter)
  yield* Ref.set(counter, n + 1)

  // update (void) / updateAndGet (returns new value)
  yield* Ref.update(counter, (x) => x + 1)
  const next = yield* Ref.updateAndGet(counter, (x) => x * 2)

  // modify — atomic read-modify-write, returns extra value
  const [old, _] = [
    yield* Ref.modify(counter, (x) => [x, x + 1]),  // returns old value, sets to old+1
  ]

  // Ref is itself an Effect — yields current value
  const current = yield* counter

  return current
})
```

### Key operations

| API | Returns | Notes |
|---|---|---|
| `Ref.make(initial)` | `Effect<Ref<A>>` | constructor |
| `Ref.get(ref)` | `Effect<A>` | |
| `Ref.set(ref, value)` | `Effect<void>` | |
| `Ref.update(ref, f)` | `Effect<void>` | pure f only |
| `Ref.updateAndGet(ref, f)` | `Effect<A>` | returns new value |
| `Ref.getAndUpdate(ref, f)` | `Effect<A>` | returns old value |
| `Ref.modify(ref, f: A => [B, A])` | `Effect<B>` | atomic read + write |
| `Ref.updateSome(ref, f)` | `Effect<void>` | f returns `Option<A>` |
| `Ref.unsafeMake(value)` | `Ref<A>` | synchronous, no Effect |

❌ Don't use `Ref` with an effectful update function — use `SynchronizedRef` instead.
✅ `Ref.modify` is the primitive; `update`/`updateAndGet` are derived from it.

---

## `SynchronizedRef<A>` — effectful atomic updates

Same as `Ref` but exposes `updateEffect` / `modifyEffect` — the entire read-modify-write happens inside a single acquired lock so no other fiber can interleave.

```ts
import { Effect, SynchronizedRef } from "effect"

const program = Effect.gen(function* () {
  const cache = yield* SynchronizedRef.make<Map<string, number>>(new Map())

  // effectful update — fetches from DB then stores atomically
  yield* SynchronizedRef.updateEffect(cache, (map) =>
    Effect.gen(function* () {
      const value = yield* fetchFromDb("key")   // Effect<number>
      return new Map(map).set("key", value)
    })
  )

  // modifyEffect — returns computed value + stores new state atomically
  const result = yield* SynchronizedRef.modifyEffect(cache, (map) =>
    Effect.gen(function* () {
      const hit = map.get("key") ?? 0
      return [hit, new Map(map).set("key", hit + 1)]
    })
  )
})
```

All pure `Ref` operations (`get`, `set`, `update`, `modify`, …) are also available on `SynchronizedRef`.

---

## `SubscriptionRef<A>` — a `Ref` you can subscribe to

A `SubscriptionRef` **is** a `SynchronizedRef` (same `get`/`set`/`update`/`modify`/`updateEffect`/`modifyEffect` surface) plus one extra member: `.changes`, a `Stream<A>` of the current value followed by every subsequent value. Reach for it when writes need to *push* to interested parties instead of being polled.

```ts
import { Effect, SubscriptionRef, Stream } from "effect"

const program = Effect.gen(function* () {
  const status = yield* SubscriptionRef.make("idle")

  // Any number of subscribers. Each gets the CURRENT value immediately,
  // then every later value. Fork them — `.changes` never completes on its own.
  yield* Effect.fork(
    Stream.runForEach(status.changes, (s) => Effect.log(`status → ${s}`))
  )

  yield* SubscriptionRef.set(status, "running")
  yield* SubscriptionRef.update(status, (s) => `${s}!`)
})
```

Because subscribing replays the current value, a late subscriber is never left blind waiting for the next write — the difference from wiring a `Ref` next to a `PubSub` by hand, which drops everything published before the subscription.

**Where state should live — the whole family, head to head:**

| Want | Use |
|---|---|
| A value fibers read when they ask | `Ref` |
| …with effectful read-modify-write, atomically | `SynchronizedRef` |
| …that other fibers must **react** to as it changes | `SubscriptionRef` (`.changes`) |
| …and the reactor is a **UI component** (re-render, derived state, loading/error) | an `@effect-atom` `Atom` — lift the ref with `Atom.subscriptionRef(ref)` rather than duplicating state → [`18-effect-atom.md`](18-effect-atom.md) |
| Events with no "current value" (each item consumed once, by one consumer) | `Queue` |
| Events broadcast to all subscribers, no replay of the current value | `PubSub` |
| **Ambient per-fiber context** — request id, trace span, a scoped override | `FiberRef` (a different axis: not shared state, one copy *per fiber*) |

`FiberRef` is the one that doesn't belong on this spectrum. The others answer "who can observe this value"; `FiberRef` answers "who owns a copy of it." If two fibers should see each other's writes, it's the wrong tool.

---

## `FiberRef<A>` — fiber-local state

Each fiber has its own independent copy. Child fibers **inherit** the parent's value at fork time. When joined, values are **merged** via the `join` function (default: keep parent's value).

```ts
import { Effect, FiberRef } from "effect"

const program = Effect.scoped(
  Effect.gen(function* () {
    // make requires Scope — cleaned up automatically
    const requestId = yield* FiberRef.make("none", {
      fork: (id) => id,             // child inherits same id
      join: (parent, _child) => parent  // parent wins on join (default)
    })

    yield* FiberRef.set(requestId, "req-123")
    const id = yield* FiberRef.get(requestId)

    // locally — temporarily override in a scoped block
    const withOverride = yield* Effect.locally(requestId, "req-456")(
      FiberRef.get(requestId)
    )
    // after locally, value reverts to "req-123"

    return { id, withOverride }
  })
)
```

### Propagation semantics

| Scenario | Child sees | Parent after join |
|---|---|---|
| `fork: identity` (default) | parent's value | unchanged |
| `fork: () => initial` | initial value | unchanged |
| `join: (p, c) => c` | n/a | child's final value |

### `Effect.locally` vs `FiberRef.locally`

`Effect.locally` is the idiomatic scoped override — it sets the value for the duration of the inner effect, then restores it:

```ts
// ✅ idiomatic
const withCtx = Effect.locally(myRef, newValue)(myEffect)

// also available: locallyWith for function-based override
const withCtx2 = Effect.locallyWith(myRef, (v) => v + 1)(myEffect)
```

---

## `Deferred<A, E>` — one-shot async variable

A `Deferred` is a write-once cell. Many fibers can `await` it; they all resume when any fiber completes it. Think `Promise` but composable.

```ts
import { Effect, Deferred, Fiber } from "effect"

const program = Effect.gen(function* () {
  const gate = yield* Deferred.make<string, Error>()

  // producer fiber
  const producer = yield* Effect.fork(
    Effect.gen(function* () {
      yield* Effect.sleep("1 second")
      yield* Deferred.succeed(gate, "hello")
    })
  )

  // consumer — blocks until gate is set
  const value = yield* Deferred.await(gate)
  // value === "hello"

  yield* Fiber.join(producer)
})
```

### Operations

| API | Notes |
|---|---|
| `Deferred.make<A, E>()` | creates unset deferred |
| `Deferred.await(d)` | suspends until set |
| `Deferred.succeed(d, value)` | complete with value, returns `Effect<boolean>` |
| `Deferred.fail(d, error)` | fail all waiters |
| `Deferred.done(d, exit)` | complete with an Exit |
| `Deferred.complete(d, effect)` | run effect, cache result |
| `Deferred.poll(d)` | returns `Option<Effect<A, E>>` — non-blocking peek |
| `Deferred.isDone(d)` | `Effect<boolean>` |
| `Deferred.interrupt(d)` | interrupt all waiters |

All completion methods return `Effect<boolean>` — `true` if this call was the one to complete it, `false` if already done.

---

## `Queue<A>` — typed async channel

Effect queues are **fiber-aware**: `offer` suspends on full (bounded), `take` suspends on empty. All operations are `Effect`s.

```ts
import { Effect, Queue } from "effect"

const program = Effect.gen(function* () {
  // Choose a strategy:
  const q1 = yield* Queue.bounded<number>(16)    // back-pressure on full
  const q2 = yield* Queue.unbounded<number>()     // grows without bound
  const q3 = yield* Queue.dropping<number>(16)   // drops new items when full
  const q4 = yield* Queue.sliding<number>(16)    // drops oldest when full

  // offer — suspends fiber if bounded + full
  const accepted = yield* Queue.offer(q1, 42)   // Effect<boolean>
  yield* q1.offerAll([1, 2, 3])                  // also on the interface

  // take — suspends if empty
  const item = yield* Queue.take(q1)             // Effect<number>

  // non-blocking batch reads
  const all = yield* Queue.takeAll(q1)           // Effect<Chunk<number>>
  const some = yield* q1.takeUpTo(5)             // Effect<Chunk<number>>

  // shutdown — interrupts waiting fibers, rejects future ops
  yield* Queue.shutdown(q1)
})
```

### Strategy comparison

| Strategy | Full behaviour | `offer` return |
|---|---|---|
| `bounded` | back-pressure (suspend) | `true` after space available |
| `unbounded` | always accepts | `true` |
| `dropping` | silently drops new item | `false` if dropped |
| `sliding` | drops oldest item | `true` |

### Consumer pattern

```ts
// Drain a queue until shutdown
const drainQueue = (q: Queue.Dequeue<number>) =>
  Effect.gen(function* () {
    while (true) {
      const item = yield* Queue.take(q)   // suspends until available
      yield* processItem(item)
    }
  }).pipe(Effect.scoped)
```

---

## `PubSub<A>` — fan-out pub/sub

Each subscriber gets **every** message published after subscribing. Back-pressure / dropping / sliding semantics available (same as Queue).

```ts
import { Effect, PubSub, Queue } from "effect"

const program = Effect.scoped(
  Effect.gen(function* () {
    const hub = yield* PubSub.bounded<string>(16)

    // subscribe returns a Queue.Dequeue scoped to the current Scope
    const sub1 = yield* hub.subscribe   // Effect<Dequeue<string>, never, Scope>
    const sub2 = yield* hub.subscribe

    // publish
    yield* hub.publish("hello")
    yield* hub.publishAll(["world", "!"])

    // each subscriber sees all published messages
    const a = yield* Queue.take(sub1)   // "hello"
    const b = yield* Queue.take(sub2)   // "hello"

    yield* PubSub.shutdown(hub)
  })
)
```

### PubSub constructors

| Constructor | Back-pressure |
|---|---|
| `PubSub.bounded(capacity)` | yes, until all subscribers consume |
| `PubSub.unbounded()` | no — can grow |
| `PubSub.dropping(capacity)` | drops new messages when full |
| `PubSub.sliding(capacity)` | drops oldest messages when full |

All constructors also accept `{ capacity, replay }` to replay the last N messages to new subscribers.

---

## `Effect.makeSemaphore` — concurrency control

A semaphore controls how many fibers can run concurrently. `makeSemaphore(1)` is a mutex.

```ts
import { Effect } from "effect"

const program = Effect.gen(function* () {
  // mutex (1 permit = exclusive access)
  const mutex = yield* Effect.makeSemaphore(1)

  const criticalSection = mutex.withPermits(1)(
    Effect.gen(function* () {
      yield* Effect.log("exclusive access")
    })
  )

  // rate-limit to 3 concurrent DB queries
  const dbSem = yield* Effect.makeSemaphore(3)
  const limitedQuery = dbSem.withPermits(1)(runQuery)

  yield* Effect.all([criticalSection, criticalSection], { concurrency: "unbounded" })
})
```

### Semaphore API

| Method | Description |
|---|---|
| `sem.withPermits(n)(effect)` | run effect with n permits, release after |
| `sem.withPermitsIfAvailable(n)(effect)` | run only if permits immediately available, returns `Option<A>` |
| `sem.take(n)` | acquire n permits (suspends) |
| `sem.release(n)` | release n permits |
| `sem.releaseAll` | release all held permits |
| `sem.resize(n)` | adjust total permits |

```ts
// ❌ don't manually take/release unless you need scoped control
// ✅ prefer withPermits — it's bracket-safe (release on interruption too)
const safe = sem.withPermits(1)(myEffect)
```

---

## `Effect.Latch` — start gate / synchronization barrier

A `Latch` is either **open** (fibers pass through) or **closed** (fibers block on `await`). It remains open once opened unless you explicitly `close` it.

```ts
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const latch = yield* Effect.makeLatch(false)   // starts closed

  // fork workers that wait for the latch
  const worker = Effect.gen(function* () {
    yield* latch.await     // blocks until open
    yield* Effect.log("worker running")
  })
  const fibers = yield* Effect.all(
    Array.from({ length: 5 }, () => Effect.fork(worker))
  )

  // release all at once
  yield* latch.open        // all workers unblock

  // optional: re-close for next round
  yield* latch.close
})
```

### Latch API

| Property | Type | Description |
|---|---|---|
| `latch.open` | `Effect<void>` | open gate, release all waiting fibers |
| `latch.close` | `Effect<void>` | close gate |
| `latch.await` | `Effect<void>` | wait until open |
| `latch.release` | `Effect<void>` | release waiters without permanently opening |
| `latch.whenOpen(effect)` | `Effect<A, E, R>` | run effect only when open |

---

## `Mailbox<A, E>` — bounded actor inbox (experimental)

A `Mailbox` is a queue that can be **signaled done or failed**, bridging between producer and stream consumer. Marked `@experimental` as of 3.8.0.

```ts
import { Effect, Mailbox } from "effect"

const program = Effect.gen(function* () {
  const mb = yield* Mailbox.make<number, string>()

  // produce
  yield* mb.offer(1)
  yield* mb.offerAll([2, 3, 4])

  // consume — takeAll blocks until messages arrive, done flag tells you when closed
  const [messages, done] = yield* mb.takeAll
  // single item
  const one = yield* mb.take        // fails with NoSuchElementException if done

  // signal completion
  yield* mb.end           // clean EOF
  yield* mb.fail("err")   // fail with error
})
```

`Mailbox` can be converted to a `Stream` for downstream processing.

---

## STM — Software Transactional Memory

Use STM when you need to **atomically modify multiple independent `TRef`s** while maintaining invariants — bank transfers, bounded buffers, etc. STM transactions retry automatically on conflict; no locks needed.

### TRef operations

```ts
import { STM, TRef, Effect } from "effect"

// TRef.make returns STM, must be committed
const program = Effect.gen(function* () {
  const balance = yield* STM.commit(TRef.make(1000))

  // pure STM operations — return STM<A>, not Effect<A>
  const val = yield* STM.commit(TRef.get(balance))
  yield* STM.commit(TRef.set(balance, 500))
  yield* STM.commit(TRef.update(balance, (n) => n - 100))
  const next = yield* STM.commit(TRef.updateAndGet(balance, (n) => n + 50))
  const old = yield* STM.commit(TRef.modify(balance, (n) => [n, n * 2]))
})
```

### Composing transactions with `STM.gen`

The power of STM is **composing multiple TRef reads/writes into one atomic transaction**:

```ts
import { STM, TRef, Effect } from "effect"

// Classic bank transfer — impossible to race between accounts
const transfer = (
  from: TRef.TRef<number>,
  to: TRef.TRef<number>,
  amount: number
) =>
  STM.gen(function* () {
    const balance = yield* TRef.get(from)
    // STM.check causes retry if condition is false
    yield* STM.check(() => balance >= amount)
    yield* TRef.update(from, (n) => n - amount)
    yield* TRef.update(to, (n) => n + amount)
  })

const program = Effect.gen(function* () {
  const alice = yield* STM.commit(TRef.make(1000))
  const bob   = yield* STM.commit(TRef.make(500))

  // Runs atomically — no intermediate state visible to other fibers
  yield* STM.commit(transfer(alice, bob, 200))

  const [a, b] = yield* STM.commit(
    STM.gen(function* () {
      return [yield* TRef.get(alice), yield* TRef.get(bob)] as const
    })
  )
  // a === 800, b === 700
})
```

### Why STM beats `Ref` for multi-variable invariants

```ts
// ❌ Wrong — two separate Ref.update calls are NOT atomic
//    Another fiber can observe alice=800, bob=500 between the two updates
yield* Ref.update(aliceRef, (n) => n - 200)
yield* Ref.update(bobRef,   (n) => n + 200)

// ✅ Correct — STM makes all TRef reads/writes appear instantaneous
yield* STM.commit(transfer(alice, bob, 200))
```

### STM primitives

| API | Description |
|---|---|
| `TRef.make(value)` | `STM<TRef<A>>` — create a TRef |
| `TRef.get(ref)` | `STM<A>` |
| `TRef.set(ref, value)` | `STM<void>` |
| `TRef.update(ref, f)` | `STM<void>` |
| `TRef.modify(ref, f)` | `STM<B>` |
| `STM.gen(function*() {...})` | compose STM operations |
| `STM.commit(stm)` | `Effect<A, E, R>` — execute transaction |
| `STM.check(predicate)` | retry transaction if false |
| `STM.retry` | unconditionally retry |
| `STM.orElse(stm1, stm2)` | try stm1, fall back to stm2 |

---

## Quick selection guide

| Need | Tool |
|---|---|
| Shared counter / config | `Ref` |
| Shared cache with async lookup | `SynchronizedRef` |
| Shared value others must react to as it changes | `SubscriptionRef` (`.changes` is a `Stream`) |
| …and the reactive consumer is the UI | `SubscriptionRef` → `@effect-atom` ([`18`](18-effect-atom.md)) |
| Per-request context (e.g. tracing, auth) | `FiberRef` + `Effect.locally` |
| "Signal when ready" (one-shot) | `Deferred` |
| Work queue (producer/consumer) | `Queue.bounded` |
| Event fan-out | `PubSub` |
| Limit concurrency / mutex | `Effect.makeSemaphore` |
| Start gate (release N fibers at once) | `Effect.makeLatch` |
| Actor inbox with backpressure + EOF | `Mailbox` |
| Multi-variable atomic invariant | `STM` + `TRef` |

---

## See also

- `09-scheduling-time.md` — `Effect.sleep`, `Schedule`, `Duration`
- `07-concurrency-fibers.md` — `Effect.fork`, `Fiber`, `Effect.all`
- `packages/effect/test/Effect/latch.test.ts` — latch integration tests
- `packages/effect/test/FiberRef.test.ts` — fork/join propagation examples
- `packages/effect/test/Deferred.test.ts`
- `packages/effect/test/Effect/caching.test.ts`
