# effect-atom — reactive state for Effect

Reach for `@effect-atom/atom` when you need reactive, composable, lazily-evaluated state that is natively backed by `Effect`, `Stream`, and `Layer`-provided services — and want that state to propagate live updates into a UI framework (SolidJS, React, Vue) without writing any subscription glue.

> **Ecosystem add-on, not core Effect.** `@effect-atom/atom` is a third-party library by Tim Smart (v0.5.x). It is not part of the `effect` core package. Install it separately.

---

## Contents

- [Mental model](#mental-model)
- [Installation](#installation)
- [Core API — `@effect-atom/atom`](#core-api-effect-atomatom)
- [The `Result` type](#the-result-type)
- [The `Registry`](#the-registry)
- [React bindings — `@effect-atom/atom-react`](#react-bindings-effect-atomatom-react)
- [SolidJS bindings — `@effect-atom/atom-solid` (primary binding)](#solidjs-bindings-effect-atomatom-solid-primary-binding)
- [Vue bindings — `@effect-atom/atom-vue`](#vue-bindings-effect-atomatom-vue)
- [`@effect-atom/atom-livestore` — LiveStore integration](#effect-atomatom-livestore-livestore-integration)
- [Effect / Stream / Layer integration deep-dive](#effect-stream-layer-integration-deep-dive)
- [When to reach for effect-atom](#when-to-reach-for-effect-atom)
- [See also](#see-also)


## Mental model

An `Atom<A>` is a lazy, observable cell:

- **Synchronous atoms** hold a plain value or a derived computation over other atoms.
- **Async atoms** (backed by an `Effect` or `Stream`) hold a `Result<A, E>` — a three-state value representing loading/success/failure.
- **Writable atoms** extend `Atom<R>` with a `write` handler, making them two-way.
- All atoms are **reference-stable** objects. The `Registry` evaluates them on demand and caches the live computation. When dependencies change the registry re-runs the atom's `read` function and notifies subscribers.

```
Atom<A> ─── read (get: Context) => A
Writable<R, W> extends Atom<R> ─── read + write
AtomRuntime<R> ─── Atom wrapping a Layer-built Runtime<R>
Result<A, E> = Initial | Success | Failure
```

The `Registry` is the evaluation engine. In a UI app you normally never create one directly — `RegistryProvider` does it for you. In tests or server code you call `Registry.make()`.

---

## Installation

```bash
# Core (framework-agnostic)
pnpm add @effect-atom/atom

# SolidJS bindings (primary binding)
pnpm add @effect-atom/atom-solid

# React bindings
pnpm add @effect-atom/atom-react
```

Peer deps: `effect`, `solid-js` or `react`.

---

## Core API — `@effect-atom/atom`

All imports below come from `"@effect-atom/atom"` unless noted.

### `Atom.make` — the universal constructor

`Atom.make` is overloaded to accept six different input shapes:

```ts
import { Atom } from "@effect-atom/atom"
import { Effect, Stream, Schedule } from "effect"

// 1. Plain value → Writable<number>
const countAtom = Atom.make(0)

// 2. Derived sync — function of Context → Atom<number>
const doubleAtom = Atom.make((get) => get(countAtom) * 2)

// 3. Effect → Atom<Result<string, HttpError>>
const dataAtom = Atom.make(
  Effect.gen(function* () {
    const res = yield* fetchUser(1)
    return res.name
  })
)

// 4. Effect factory — receives Context so it can read other atoms
const derivedDataAtom = Atom.make(
  Effect.fnUntraced(function* (get: Atom.Context) {
    const id = get(idAtom) // re-runs when idAtom changes
    return yield* fetchUser(id)
  })
)

// 5. Stream → Atom<Result<number, never>>  (latest emitted value)
const tickAtom = Atom.make(Stream.fromSchedule(Schedule.spaced(1000)))

// 6. Stream factory
const liveAtom = Atom.make((get) =>
  Stream.fromIterable([get(countAtom), get(countAtom) + 1])
)
```

**Type rule:** plain value → `Writable<A>`. Function/Effect/Stream → `Atom<Result<A, E>>` (for async) or `Atom<A>` (for sync function).

---

### `Atom.make` with a `get` function — the `Context` parameter

The `get` argument passed to a read function is `Atom.Context`. Key methods:

| Method | What it does |
|---|---|
| `get(otherAtom)` / `get.get(atom)` | Read another atom synchronously; creates a dependency |
| `get.result(resultAtom)` | Await a `Result` atom inside an `Effect` |
| `get.once(atom)` | Read without creating a dependency |
| `get.addFinalizer(fn)` | Run cleanup when this atom is rebuilt or disposed |
| `get.setSelf(value)` | Push a new value to this atom from inside the reader |
| `get.refresh(atom)` | Force-recompute another atom |
| `get.refreshSelf()` | Re-run this atom |
| `get.mount(atom)` | Keep an atom alive while this one is alive |
| `get.stream(atom)` | Get a `Stream<A>` of another atom's changes |
| `get.subscribe(atom, fn)` | Subscribe imperatively (returns unsub when passed `addFinalizer`) |
| `get.registry` | Access the raw `Registry` |

---

### `Atom.writable` — custom read + write

```ts
import { Atom } from "@effect-atom/atom"

// Writable<R, W> where R is the read type, W is the write type
const uppercaseAtom = Atom.writable<string, string>(
  (get) => get(nameAtom).toUpperCase(),
  (ctx, value) => {
    ctx.set(nameAtom, value.toLowerCase())
  }
)
```

---

### `Atom.readable` — read-only with optional refresh hook

```ts
const scrollYAtom = Atom.readable(
  (get) => {
    const onScroll = () => get.setSelf(window.scrollY)
    window.addEventListener("scroll", onScroll)
    get.addFinalizer(() => window.removeEventListener("scroll", onScroll))
    return window.scrollY
  }
)
```

---

### `Atom.fn` — action atoms (run an Effect on demand)

`Atom.fn` creates a `Writable` (an `AtomResultFn`) that runs an Effect when written. The result of the last invocation is held as `Result<A, E>`.

```ts
import { Atom } from "@effect-atom/atom"
import { Effect } from "effect"

// Arg = number, returns Result<void, never>
const logAtom = Atom.fn(
  Effect.fnUntraced(function* (arg: number) {
    yield* Effect.log("got arg", arg)
  })
)

// Using it in React — but same pattern applies in Solid
// const log = useAtomSet(logAtom)  → log(42)
```

To cancel the running effect, send the sentinel `Atom.Reset` or `Atom.Interrupt`.

**`Atom.fn` options:**

```ts
Atom.fn(effect, {
  initialValue: undefined, // pre-populate the Result before first call
  concurrent: false,       // when true, new invocations don't cancel in-flight ones
})
```

---

### `Atom.fnSync` — synchronous action atom

```ts
const parseAtom = Atom.fnSync((input: string) => parseInt(input, 10), {
  initialValue: 0
})
// type: Writable<number, string>
```

---

### `Atom.pull` — paginated / chunked stream

`pull` wraps a `Stream` into a `Writable<PullResult<A, E>, void>`. Each time you call the setter it pulls the next chunk.

```ts
const listAtom = Atom.pull(fetchPagedStream())
// PullResult<A, E> = Result<{ done: boolean; items: NonEmptyArray<A> }, E>
```

---

### `Atom.family` — stable atom references per key

Atoms are compared by **reference**. `Atom.family` memoises the factory per argument, returning the same atom object for equal keys (uses `WeakRef` + `FinalizationRegistry`).

```ts
const userAtom = Atom.family((id: string) =>
  runtimeAtom.atom(
    Effect.gen(function* () {
      const users = yield* Users
      return yield* users.findById(id)
    })
  )
)

// userAtom("1") === userAtom("1")  ✅ stable reference
```

---

### Lifecycle — `keepAlive` vs auto-dispose

By default, an atom is **disposed** (torn down, finalizers run) when its last subscriber unmounts. Use `Atom.keepAlive` to retain state across unmounts.

```ts
const persistentAtom = Atom.make(0).pipe(Atom.keepAlive)
```

`Atom.autoDispose` reverts `keepAlive` on an atom.

`Atom.setIdleTTL` keeps the atom alive for a grace period after its last subscriber leaves, then disposes it:

```ts
const cachedAtom = Atom.make(fetchData()).pipe(
  Atom.setIdleTTL("30 seconds")
)
```

`Atom.setLazy` defers computation until the first subscriber arrives (atoms are eager by default).

---

### Combinators cheat-sheet

| API | What it returns |
|---|---|
| `Atom.map(atom, f)` | Derived atom, preserves Writable |
| `Atom.mapResult(atom, f)` | Map the `Success` value inside a `Result` atom |
| `Atom.transform(atom, (get) => ...)` | Like map but gets full `Context` |
| `Atom.withFallback(atom, fallbackAtom)` | Use fallback `Result` while primary is `Initial` |
| `Atom.debounce(atom, "500 millis")` | Debounce value propagation |
| `Atom.withLabel(atom, "name")` | Debugging label |
| `Atom.initialValue(atom, value)` | Seed a Result atom with an initial success value |
| `Atom.refreshOnWindowFocus` | Re-run on window focus |
| `Atom.makeRefreshOnSignal(signalAtom)` | Re-run when a signal atom changes |
| `Atom.batch(fn)` | Batch multiple writes into a single notification |
| `Atom.refresh(atom)` | Force-recompute (returns `Effect<void, never, AtomRegistry>`) |
| `Atom.get(atom)` | Read current value as `Effect<A, never, AtomRegistry>` |
| `Atom.set(atom, value)` | Write as `Effect<void, never, AtomRegistry>` |
| `Atom.update(atom, f)` | Update-fn as `Effect<void, never, AtomRegistry>` |
| `Atom.toStream(atom)` | Get a `Stream<A, never, AtomRegistry>` |
| `Atom.toStreamResult(atom)` | `Stream<A, E, AtomRegistry>` from a `Result` atom |

---

### `Atom.runtime` — connecting Effect services via Layer

`Atom.runtime` is a `RuntimeFactory`. Call it with a `Layer` to get an `AtomRuntime<R>`.

```ts
import { Atom } from "@effect-atom/atom"
import { Effect } from "effect"

class Users extends Effect.Service<Users>()("app/Users", {
  effect: Effect.succeed({
    findById: (id: string) => Effect.succeed({ id, name: "Alice" })
  })
}) {}

//       ┌─── AtomRuntime<Users>
const runtimeAtom = Atom.runtime(Users.Default)

// Creates atoms that can yield* Users directly
const userAtom = runtimeAtom.atom(
  Effect.gen(function* () {
    const users = yield* Users
    return yield* users.findById("1")
  })
)

// Creates fn atoms that resolve against the Layer
const createUserAtom = runtimeAtom.fn(
  Effect.fnUntraced(function* (name: string) {
    const users = yield* Users
    return yield* users.create(name)
  }),
  { reactivityKeys: ["users"] } // optional: invalidate "users" key when done
)
```

`Atom.runtime.addGlobalLayer` installs cross-cutting infrastructure (loggers, config providers, tracers) before any `AtomRuntime` is built:

```ts
Atom.runtime.addGlobalLayer(
  Layer.setConfigProvider(ConfigProvider.fromJson(import.meta.env))
)
```

---

### Scoped effects — finalizers on atom lifecycle

Every effectful atom receives a `Scope`. Add finalizers to clean up subscriptions, timers, connections:

```ts
const wsAtom = Atom.make(
  Effect.gen(function* () {
    const ws = yield* openWebSocket("wss://example.com")
    yield* Effect.addFinalizer(() => Effect.sync(() => ws.close()))
    return ws
  })
)
```

The finalizer runs when the atom is rebuilt (its deps changed) or disposed.

---

### `Atom.optimistic` — optimistic UI

```ts
const listAtom = Atom.make(fetchItems())
const optimisticList = Atom.optimistic(listAtom)
// type: Writable<A, Atom<Result<A, unknown>>>
```

`Atom.optimisticFn` pairs an `Atom.fn` with a reducer for client-side prediction.

---

### `Atom.searchParam` — URL search parameter atom

```ts
import { Atom } from "@effect-atom/atom"
import { Schema } from "effect"

// Writable<string>
const qAtom = Atom.searchParam("q")

// Writable<Option<number>>
const pageAtom = Atom.searchParam("page", { schema: Schema.NumberFromString })
```

---

### `Atom.kvs` — localStorage atom

```ts
import { Atom } from "@effect-atom/atom"
import { BrowserKeyValueStore } from "@effect/platform-browser"
import { Schema } from "effect"

const runtime = Atom.runtime(BrowserKeyValueStore.layerLocalStorage)

const darkModeAtom = Atom.kvs({
  runtime,
  key: "dark-mode",
  schema: Schema.Boolean,
  defaultValue: () => false,
})
// type: Writable<boolean, boolean>
```

---

### `Atom.subscriptionRef` / `Atom.subscribable` — bridge from Effect

```ts
// Wraps an existing SubscriptionRef into a Writable atom
const subRefAtom = Atom.subscriptionRef(mySubscriptionRef)

// Wraps a Subscribable (hot, no initial value problem)
const subAtom = Atom.subscribable(mySubscribable)
```

---

## The `Result` type

Every async atom (`Effect` or `Stream` backed) produces `Result<A, E>`. This is a **three-state discriminated union**:

```ts
type Result<A, E> = Initial<A, E> | Success<A, E> | Failure<A, E>
```

| Variant | `_tag` | Fields | `waiting` flag |
|---|---|---|---|
| `Initial` | `"Initial"` | — | `true` while first load in progress |
| `Success` | `"Success"` | `value: A`, `timestamp: number` | `true` if refreshing |
| `Failure` | `"Failure"` | `cause: Cause<E>`, `previousSuccess: Option<Success>` | `true` if retrying |

**Note:** `waiting` on any variant means a computation is in flight (useful for skeleton states). `previousSuccess` on `Failure` lets you show stale data while displaying the error.

### Pattern-matching

```ts
import { Result } from "@effect-atom/atom"
import { Cause } from "effect"

// Functional match
Result.match(result, {
  onInitial: (_) => "loading...",
  onFailure: (f) => `error: ${Cause.pretty(f.cause)}`,
  onSuccess: (s) => `value: ${s.value}`,
})

// Builder (fluent, only handles what you care about)
Result.builder(result)
  .onInitial(() => <Spinner />)
  .onFailure((cause) => <Error message={Cause.pretty(cause)} />)
  .onSuccess((value) => <Data value={value} />)
  .render()

// onError vs onDefect (matchWithError distinguishes typed errors from defects)
Result.matchWithError(result, {
  onInitial: (_) => "...",
  onError: (err, _) => `typed error: ${err}`,
  onDefect: (defect, _) => `unexpected: ${String(defect)}`,
  onSuccess: (s) => s.value,
})

// matchWithWaiting — collapse initial + refreshing into one case
Result.matchWithWaiting(result, {
  onWaiting: (_) => <Spinner />,
  onError: (err) => <Error />,
  onDefect: (defect) => <Crash />,
  onSuccess: (s) => <Data value={s.value} />,
})
```

### Accessors

```ts
Result.getOrElse(result, () => fallback) // A | B
Result.getOrThrow(result)                // A, throws on non-success
Result.value(result)                     // Option<A>
Result.cause(result)                     // Option<Cause<E>>
Result.error(result)                     // Option<E>
Result.isInitial(result)                 // boolean
Result.isSuccess(result)                 // boolean
Result.isFailure(result)                 // boolean
Result.isWaiting(result)                 // boolean
```

### Combining results

```ts
// Combines [Result<A>, Result<B>] → Result<[A, B]>
const combined = Result.all([usersResult, postsResult])

// Map the success value
const mapped = Result.map(result, (user) => user.name)
```

---

## The `Registry`

The `Registry` is the evaluation engine. You interact with it directly in tests or server-side rendering; in UI apps the provider creates and manages it.

```ts
import { Registry } from "@effect-atom/atom"

const registry = Registry.make({
  // optional
  initialValues: [[countAtom, 42]],      // seed atoms before first read
  defaultIdleTTL: 5 * 60 * 1000,        // ms before idle atoms are disposed
  scheduleTask: requestAnimationFrame,   // how to schedule UI updates
})

registry.get(countAtom)          // read current value
registry.set(writableAtom, val)  // write
registry.update(writableAtom, f) // update-fn
registry.refresh(atom)           // force recompute
registry.mount(atom)             // keep alive, returns () => void cleanup
registry.subscribe(atom, fn)     // subscribe, returns () => void cleanup
registry.dispose()               // tear down everything
```

`Registry.layer` provides `AtomRegistry` as an Effect service for use in tests.

---

## React bindings — `@effect-atom/atom-react`

```ts
import {
  Atom, Result,
  useAtom, useAtomValue, useAtomSet, useAtomRefresh,
  useAtomMount, useAtomSubscribe, useAtomSuspense,
  RegistryProvider, RegistryContext,
} from "@effect-atom/atom-react"
```

### `RegistryProvider`

Wrap your app (or subtree) once. Creates a `Registry` scoped to the component tree.

```tsx
import { RegistryProvider } from "@effect-atom/atom-react"

export function App() {
  return (
    <RegistryProvider
      defaultIdleTTL={5 * 60 * 1000} // optional
    >
      <Routes />
    </RegistryProvider>
  )
}
```

### Core hooks

| Hook | Signature | Notes |
|---|---|---|
| `useAtomValue(atom)` | `A` | Subscribe + re-render on change. Optionally pass a selector as 2nd arg |
| `useAtomSet(atom)` | `(W \| (R→W)) => void` | Write-only, no re-render on read |
| `useAtom(atom)` | `[R, setter]` | Read + write together |
| `useAtomRefresh(atom)` | `() => void` | Force-recompute trigger |
| `useAtomMount(atom)` | `void` | Keep atom alive for this component's lifetime |
| `useAtomSubscribe(atom, fn)` | `void` | Imperative subscribe, no re-render |
| `useAtomSuspense(atom)` | `Success<A, E>` | Integrates with React Suspense |
| `useAtomInitialValues(pairs)` | `void` | Seed values on first mount |

### `useAtomSet` modes

```ts
// Default: void setter
const setCount = useAtomSet(countAtom)
setCount((n) => n + 1)

// mode: "promise" — resolves to Success value when done
const save = useAtomSet(saveFnAtom, { mode: "promise" })
const result = await save(payload)

// mode: "promiseExit" — resolves to Exit (safe, no throw)
const save = useAtomSet(saveFnAtom, { mode: "promiseExit" })
const exit = await save(payload)
if (Exit.isSuccess(exit)) console.log(exit.value)
```

### Worked example: counter

```tsx
import { Atom, useAtomValue, useAtomSet } from "@effect-atom/atom-react"

const countAtom = Atom.make(0).pipe(Atom.keepAlive)

function Counter() {
  const count = useAtomValue(countAtom)
  return <h1>{count}</h1>
}

function IncrementButton() {
  const setCount = useAtomSet(countAtom)
  return <button onClick={() => setCount((n) => n + 1)}>+</button>
}
```

### Worked example: async data fetch

```tsx
import { Atom, Result, useAtomValue } from "@effect-atom/atom-react"
import { Effect } from "effect"
import { Cause } from "effect"

// Atom backed by a service in an AtomRuntime
const usersAtom = runtimeAtom.atom(
  Effect.gen(function* () {
    const users = yield* Users
    return yield* users.getAll
  })
)

function UserList() {
  const result = useAtomValue(usersAtom)

  return Result.builder(result)
    .onInitial(() => <div>Loading...</div>)
    .onFailure((cause) => <div>Error: {Cause.pretty(cause)}</div>)
    .onSuccess((users) => (
      <ul>{users.map((u) => <li key={u.id}>{u.name}</li>)}</ul>
    ))
    .render()
}
```

### `ScopedAtom` — per-subtree atom instance (React only)

```tsx
import { ScopedAtom } from "@effect-atom/atom-react"

const LocalCount = ScopedAtom.make(() => Atom.make(0))

function Widget() {
  return (
    <LocalCount.Provider>
      <Counter />
    </LocalCount.Provider>
  )
}

function Counter() {
  const countAtom = LocalCount.use()
  const count = useAtomValue(countAtom)
  return <span>{count}</span>
}
```

### SSR hydration (React)

```tsx
import { HydrationBoundary } from "@effect-atom/atom-react"

// server.tsx
import { Hydration, Registry } from "@effect-atom/atom"
const registry = Registry.make()
const state = Hydration.dehydrate(registry)

// client.tsx
<RegistryProvider>
  <HydrationBoundary state={serverState}>
    <App />
  </HydrationBoundary>
</RegistryProvider>
```

---

## SolidJS bindings — `@effect-atom/atom-solid` (primary binding)

```ts
import {
  Atom, Result, AtomRef,
  useAtom, useAtomValue, useAtomSet, useAtomRefresh,
  useAtomMount, useAtomSubscribe,
  useAtomRef, useAtomRefProp, useAtomRefPropValue,
  useAtomInitialValues,
  RegistryProvider, RegistryContext,
} from "@effect-atom/atom-solid"
```

**Key difference from React:** `useAtomValue` returns a SolidJS `Accessor<A>` (a signal getter function), not a raw value. Call it to read: `count()`.

### `RegistryProvider` (Solid)

```tsx
import { RegistryProvider } from "@effect-atom/atom-solid"

export function App() {
  return (
    <RegistryProvider defaultIdleTTL={5 * 60 * 1000}>
      <Routes />
    </RegistryProvider>
  )
}
```

The provider creates a `Registry` on mount and calls `registry.dispose()` in `onCleanup` automatically.

### Core primitives

| Function | Return type | Notes |
|---|---|---|
| `useAtomValue(atom)` | `Accessor<A>` | Reactive signal; call `value()` to read |
| `useAtomValue(atom, selector)` | `Accessor<B>` | Map inside the hook |
| `useAtomSet(atom)` | setter fn | Also mounts the atom |
| `useAtom(atom)` | `readonly [Accessor<R>, setter]` | Read + write |
| `useAtomRefresh(atom)` | `() => void` | Force-recompute; mounts the atom |
| `useAtomMount(atom)` | `void` | Keep atom alive for this component's lifetime (`onCleanup` unmounts) |
| `useAtomSubscribe(atom, fn)` | `void` | Imperative subscribe; cleaned up on `onCleanup` |
| `useAtomInitialValues(pairs)` | `void` | Seed atoms before first read (run top-of-component) |

### Worked example: counter (Solid)

```tsx
import { Atom, useAtomValue, useAtomSet } from "@effect-atom/atom-solid"
import type { Component } from "solid-js"

const countAtom = Atom.make(0).pipe(Atom.keepAlive)

const Counter: Component = () => {
  const count = useAtomValue(countAtom)
  // count is Accessor<number> — call count() to read
  return <h1>{count()}</h1>
}

const IncrementButton: Component = () => {
  const setCount = useAtomSet(countAtom)
  return <button onClick={() => setCount((n) => n + 1)}>+</button>
}
```

### Worked example: async users list (Solid)

```tsx
import { Atom, Result, useAtomValue, RegistryProvider } from "@effect-atom/atom-solid"
import { Effect } from "effect"
import { Cause } from "effect"
import { Show, For } from "solid-js"

// --- service + runtime setup (shared module) ---
class Users extends Effect.Service<Users>()("app/Users", {
  effect: Effect.succeed({
    getAll: Effect.succeed([
      { id: "1", name: "Alice" },
      { id: "2", name: "Bob" },
    ])
  })
}) {}

const runtimeAtom = Atom.runtime(Users.Default)

const usersAtom = runtimeAtom.atom(
  Effect.gen(function* () {
    const users = yield* Users
    return yield* users.getAll
  })
)

// --- component ---
const UserList: Component = () => {
  const result = useAtomValue(usersAtom)
  // result is Accessor<Result<User[], never>>

  return (
    <>
      {Result.match(result(), {
        onInitial: () => <div>Loading...</div>,
        onFailure: (f) => <div>Error: {Cause.pretty(f.cause)}</div>,
        onSuccess: (s) => (
          <ul>
            <For each={s.value}>{(u) => <li>{u.name}</li>}</For>
          </ul>
        ),
      })}
    </>
  )
}
```

### Worked example: fn atom / mutation (Solid)

```tsx
import { Atom, Result, useAtom, useAtomSet } from "@effect-atom/atom-solid"
import { Effect, Exit } from "effect"
import { Show } from "solid-js"

const createUserAtom = runtimeAtom.fn(
  Effect.fnUntraced(function* (name: string) {
    const users = yield* Users
    return yield* users.create(name)
  })
)

const CreateUser: Component = () => {
  // useAtomSet returns the write function; fn result is tracked separately
  const create = useAtomSet(createUserAtom, { mode: "promiseExit" })

  const handleClick = async () => {
    const exit = await create("Charlie")
    if (Exit.isSuccess(exit)) {
      console.log("created:", exit.value)
    }
  }

  return <button onClick={handleClick}>Create user</button>
}
```

### Worked example: pull / infinite scroll (Solid)

```tsx
import { Atom, Result, useAtom } from "@effect-atom/atom-solid"
import { Stream } from "effect"
import { Show, For } from "solid-js"

const itemsAtom = Atom.pull(Stream.make(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
// type: Writable<PullResult<number, never>, void>

const InfiniteList: Component = () => {
  const [result, loadMore] = useAtom(itemsAtom)

  return (
    <>
      {Result.match(result(), {
        onInitial: () => <div>Loading first page...</div>,
        onFailure: (f) => <div>Error</div>,
        onSuccess: (s) => (
          <>
            <ul>
              <For each={s.value.items}>{(item) => <li>{item}</li>}</For>
            </ul>
            <Show when={!s.value.done}>
              <button onClick={() => loadMore()}>Load more</button>
            </Show>
          </>
        ),
      })}
    </>
  )
}
```

### `AtomRef` — lightweight mutable ref (Solid + React)

`AtomRef` is a plain reactive cell **outside** the registry, useful for component-local mutable state that doesn't need Effect integration.

```ts
import { AtomRef, useAtomRef } from "@effect-atom/atom-solid"

const nameRef = AtomRef.make("Alice")

const NameDisplay: Component = () => {
  const name = useAtomRef(nameRef) // Accessor<string>
  return <span>{name()}</span>
}

// Mutations — AtomRef is immutable-update style
nameRef.set("Bob")
nameRef.update((n) => n.toUpperCase())
nameRef.prop("firstName") // creates a child AtomRef focused on a key
```

`AtomRef.collection` gives you an ordered list of `AtomRef` items with `push`, `insertAt`, `remove`.

---

## Vue bindings — `@effect-atom/atom-vue`

```ts
import {
  Atom, Result,
  useAtom, useAtomValue, useAtomSet, useAtomRef,
  injectRegistry, registryKey, defaultRegistry,
} from "@effect-atom/atom-vue"
```

Vue composables take **getter functions** (`() => atom`) instead of the atom directly, matching Vue's reactivity model.

```ts
// Vue: atom wrapped in getter
const count = useAtomValue(() => countAtom) // Readonly<Ref<number>>
const [value, set] = useAtom(() => writableAtom)
const setter = useAtomSet(() => writableAtom)
```

Registry injection uses Vue's provide/inject:

```ts
// In setup
const registry = injectRegistry() // inject from ancestor
// defaultRegistry is the module-level singleton
```

---

## `@effect-atom/atom-livestore` — LiveStore integration

`AtomLivestore.Tag` creates an `AtomRuntime`-aware LiveStore handle that exposes `store`, `makeQuery`, and `commit` as atoms.

```ts
import { AtomLivestore } from "@effect-atom/atom-livestore"

class AppStore extends AtomLivestore.Tag<AppStore>()(
  "AppStore",
  { schema: mySchema, /* CreateStoreOptions */ }
) {}

// AppStore.store    → Atom<Result<Store>>
// AppStore.makeQuery(query) → Atom<Result<QueryResult>>
// AppStore.commit   → Writable<void, CommitPayload>
// AppStore.runtime  → AtomRuntime<AppStore>
```

---

## Effect / Stream / Layer integration deep-dive

### How errors land in `Result.Failure`

Both typed errors (`E` channel) and defects (unexpected throws) become `Result.Failure` with a `Cause<E>`. Use `Result.matchWithError` to distinguish them.

### Interruption on unmount

When a component unmounts (or `keepAlive` is false and there are no more subscribers), the atom's `Scope` is closed. This interrupts any running fiber, triggering all `addFinalizer`/`Effect.addFinalizer` callbacks. Network requests, WebSocket connections, and timers are all cleaned up automatically.

### Providing a runtime to atoms

```
Layer → Atom.runtime(layer) → AtomRuntime<R>
       → .atom(effect)      → Atom<Result<A, E | ER>>
       → .fn(effect)        → AtomResultFn<Arg, A, E | ER>
       → .pull(stream)      → Writable<PullResult<A, E | ER>, void>
```

The `AtomRuntime` is itself an `Atom<Result<Runtime<R>, ER>>` — it lazily builds the Layer when first needed and caches the result.

### `Atom.withReactivity` — cache invalidation

```ts
import { Reactivity } from "@effect/experimental"

// Refresh when key changes
const listAtom = runtimeAtom.atom(fetchItems()).pipe(
  Atom.withReactivity(["items"])
)

// Mutation that invalidates
const addItem = runtimeAtom.fn(
  Effect.fnUntraced(function* (item) {
    yield* ItemService.add(item)
    // manual: yield* Reactivity.invalidate(["items"])
  }),
  { reactivityKeys: ["items"] } // automatic on completion
)
```

---

## When to reach for effect-atom

| Scenario | Reach for |
|---|---|
| Local UI state with no async | SolidJS `createSignal` / React `useState` |
| A single shared value the UI never observes | `Ref` — or `SubscriptionRef` if Effect-side consumers react to it ([`08`](08-state-coordination.md)) |
| Effect-side state that ALSO drives the UI | keep the `SubscriptionRef` as the source of truth and lift it: `Atom.subscriptionRef(ref)` — don't mirror it into a second atom |
| Async data fetched from an Effect service, reactive to dependency changes | **effect-atom** `runtimeAtom.atom(effect)` |
| Live-updating data from a `Stream` | **effect-atom** `Atom.make(stream)` |
| Action that runs an Effect and tracks its loading/error state in the UI | **effect-atom** `Atom.fn` / `runtimeAtom.fn` |
| Cross-component shared state with auto-cleanup on last unmount | **effect-atom** (default lifecycle beats manual cleanup) |
| Derived / computed state across multiple async sources | **effect-atom** derived atoms (`get(a) + get(b)`) |
| Paginated / infinite scroll | **effect-atom** `Atom.pull` |

**effect-atom adds value over plain `Ref`/services when:**
- The data needs to be observed by multiple components with automatic re-render.
- You want derived state to update reactively when its inputs change.
- You want lifecycle-tied cleanup (dispose on unmount) without writing subscription boilerplate.
- You want `Result` semantics (loading/error/success) threaded through the UI automatically.

---

## See also

- [Context & Layers](05-context-layers.md)
- [Streams](10-streams.md)
- [Error handling](04-errors.md)
- [Resources & Scope](06-resources-scope.md)
- [Creating & running Effects](02-creating-running.md)
- Upstream docs: https://tim-smart.github.io/effect-atom/atom/
