# Reactivity Primitives

The keystone chapter: every reactive primitive `solid-js` exposes — `createSignal`, `createMemo`, `createEffect`, the rarer `createRenderEffect`/`createComputed`, and the utilities `on`, `untrack`, `batch`, `createReaction`. What each does, its exact signature, when to reach for it, and the cardinal rules that keep a Solid codebase clean.

```ts
import {
  createSignal, createMemo, createEffect,
  createRenderEffect, createComputed, createReaction,
  on, untrack, batch
} from "solid-js"
```

> **The single most important rule:** reads only react when they happen **inside a tracking scope** (a memo, an effect, or a JSX render binding). A read in the once-running component body — or anywhere else untracked — is a frozen snapshot. Keep that in mind for every primitive below. (→ [`01-mental-model.md`](01-mental-model.md))

---

## Contents

- [At a glance](#at-a-glance)
- [`createSignal` — the atom of state](#createsignal-the-atom-of-state)
- [`createMemo` — cached derived value](#creatememo-cached-derived-value)
- [`createEffect` — side effects after render](#createeffect-side-effects-after-render)
- [`createEffect` to derive state is a code smell — use a memo](#createeffect-to-derive-state-is-a-code-smell-use-a-memo)
- [`createRenderEffect` and `createComputed` — the rare ones](#createrendereffect-and-createcomputed-the-rare-ones)
- [`on` — explicit dependencies and deferred first run](#on-explicit-dependencies-and-deferred-first-run)
- [`untrack` — read without subscribing](#untrack-read-without-subscribing)
- [`batch` — coalesce multiple writes into one pass](#batch-coalesce-multiple-writes-into-one-pass)
- [`createReaction` — one-shot "run once when X next changes"](#createreaction-one-shot-run-once-when-x-next-changes)
- [The accessor-passing pattern](#the-accessor-passing-pattern)
- [Recipe: debouncing / throttling a signal](#recipe-debouncing-throttling-a-signal)
- [Recipe: persisting a signal to `localStorage`](#recipe-persisting-a-signal-to-localstorage)
- [The cardinal rules](#the-cardinal-rules)
- [See also](#see-also)


## At a glance

| Primitive | Signature (simplified) | Use when… |
| --- | --- | --- |
| `createSignal` | `createSignal<T>(value?, options?) → [Accessor<T>, Setter<T>]` | You need a single piece of mutable reactive state |
| `createMemo` | `createMemo<T>(fn, value?, options?) → Accessor<T>` | You need a **cached derived value** read in multiple places or expensive to compute |
| inline accessor | `const d = () => a() * 2` | You need derived state read **once / cheaply** — no caching needed |
| `createEffect` | `createEffect<T>(fn, value?) → void` | You need a **side effect** that re-runs when its deps change (after render) |
| `createRenderEffect` | `createRenderEffect<T>(fn, value?) → void` | A side effect that must run **during** render (rare; e.g. measuring before paint) |
| `createComputed` | `createComputed<T>(fn, value?) → void` | You must write to another reactive primitive **before** render (rare; usually a memo is better) |
| `on` | `on(deps, fn, { defer? })` | You want **explicit** dependencies and/or to skip the first run (`defer`) |
| `untrack` | `untrack(fn) → T` | You need to **read without subscribing** inside a tracking scope |
| `batch` | `batch(fn) → T` | You make **multiple writes** that should notify observers once |
| `createReaction` | `createReaction(onInvalidate) → (track) => void` | You want a **one-shot** "run once when X next changes" hook |

---

## `createSignal` — the atom of state

```ts
function createSignal<T>(): Signal<T | undefined>
function createSignal<T>(value: T, options?: SignalOptions<T>): Signal<T>

type Signal<T> = [get: Accessor<T>, set: Setter<T>]
type Accessor<T> = () => T

interface SignalOptions<T> {
  equals?: false | ((prev: T, next: T) => boolean)
  name?: string
}
```

A signal is a **getter/setter pair**. Reading is calling the getter; calling it inside a tracking scope **subscribes** that scope. Writing notifies every subscriber — unless the new value is "equal" to the old one (see `equals` below).

```ts
import { createSignal } from "solid-js"

const [count, setCount] = createSignal(0)

count()            // read → 0  (and subscribes, if inside a tracking scope)
setCount(5)        // write a value
setCount(c => c + 1)   // updater form: derive from the previous value → 6
```

### The updater (functional) form

`setCount(c => c + 1)` passes a function that receives the current value and returns the next. Prefer it whenever the next value depends on the current one — it avoids reading the signal separately and is the idiomatic increment/toggle.

```ts
const [open, setOpen] = createSignal(false)
const toggle = () => setOpen(o => !o)
```

> **Storing a function in a signal?** Because the setter treats a function argument as an updater, you must wrap an actual function value: `setCallback(() => myFn)`. The outer function is the updater; it returns `myFn`.

### Reading subscribes — the whole game

```ts
import { createSignal, createEffect } from "solid-js"

const [name, setName] = createSignal("Ada")

createEffect(() => console.log("hi", name()))  // calls name() inside a tracking scope → subscribes
setName("Grace")                               // → logs "hi Grace"

const snapshot = name()                         // read in plain code → no subscription, just a value
```

### The `equals` option — controlling when a write notifies

By default Solid uses **referential equality** (`===`): writing the same value (or `===`-equal object) is a no-op and notifies nobody. Two ways to change that:

```ts
// Custom equality — only notify when the comparison says "different"
const [user, setUser] = createSignal(
  { id: 1, name: "Ada" },
  { equals: (prev, next) => prev.id === next.id }   // ignore name-only changes
)

// equals: false — ALWAYS notify, even if the value is identical
const [pinged, ping] = createSignal(undefined, { equals: false })
createEffect(() => { pinged(); console.log("ping!") })
ping()  // notifies
ping()  // notifies again, even though the value didn't change
```

`equals: false` is the idiomatic way to make a signal behave like an **event/trigger** — every write fires subscribers regardless of value. It's also how you make a signal holding a *mutated-in-place* object notify (though a [store](06-stores.md) is usually the better tool for mutable structures).

---

## `createMemo` — cached derived value

```ts
function createMemo<T>(fn: (prev: T | undefined) => T): Accessor<T>
function createMemo<T>(
  fn: (prev: T | Init) => T,
  value: Init,
  options?: MemoOptions<T>      // same shape as SignalOptions: { equals?, name? }
): Accessor<T>
```

A memo is a **read-only derived signal that caches its result**. It re-runs its function when any source it reads changes — but it only **notifies its own observers when the result changes** (per the `equals` rule, `===` by default). That second clause is the value-add: a memo *insulates* downstream computations from upstream churn.

```ts
import { createSignal, createMemo } from "solid-js"

const [first, setFirst] = createSignal("Ada")
const [last, setLast] = createSignal("Lovelace")

const fullName = createMemo(() => `${first()} ${last()}`)

fullName()   // "Ada Lovelace" — cached; reading is cheap no matter how many readers
```

### The accumulator form: `createMemo(fn, initial)`

The function receives the **previous memo value** as its argument, so a memo can fold over time:

```ts
import { createSignal, createMemo } from "solid-js"

const [value, setValue] = createSignal(0)

// Track the running maximum of everything value() has ever been
const highWater = createMemo(prev => Math.max(prev, value()), 0)
//                                  ▲ previous memo result   ▲ initial
```

### Memo vs inline accessor vs effect — the decision

| You want… | Use |
| --- | --- |
| A derived value read in **many** places, or **expensive** to compute | `createMemo` (compute once, cache, share) |
| A derived value read **once** or trivially cheap (`a() * 2`) | an **inline accessor** `() => a() * 2` — no need to allocate a memo |
| To insulate downstream work from upstream churn (notify only on *result* change) | `createMemo` (its `equals` gate is the whole point) |
| A **side effect** (DOM, logging, network, writing localStorage) | `createEffect` — **never** a memo |

```ts
// ❌ A memo with no readers and no caching benefit — just a wrapper. Use a plain accessor.
const doubled = createMemo(() => count() * 2)
// ✅
const doubled = () => count() * 2
```

```ts
// ✅ A memo that earns its keep: expensive + read in several bindings, and downstream
//    only cares when the *result* flips, not on every keystroke of `query`.
const matches = createMemo(() =>
  bigList().filter(item => item.name.includes(query()))
)
```

> **A memo must be pure.** Don't perform side effects or write other signals inside a memo — that's what effects and (rarely) `createComputed` are for. A memo computes and returns; nothing else.

---

## `createEffect` — side effects after render

```ts
function createEffect<T>(fn: (prev: T | undefined) => T, value?: T): void
```

An effect runs its function, tracks the signals it read, and **re-runs whenever any of them change**. The first run happens **after the initial render** (so the DOM exists when an effect runs). Effects are for *side effects only* — talking to the outside world: logging, network calls, manual DOM/`ref` work, persisting to storage, wiring up subscriptions.

```ts
import { createSignal, createEffect } from "solid-js"

const [count, setCount] = createSignal(0)

createEffect(() => {
  document.title = `Count: ${count()}`   // side effect: sync external state
})
```

### The accumulator form

Like memos, an effect's function receives its **previous return value**, which is handy for comparing against the last run or carrying state without a separate signal:

```ts
import { createSignal, createEffect } from "solid-js"

const [count, setCount] = createSignal(0)

createEffect(prev => {
  const next = count()
  if (next !== prev) console.log(`changed from ${prev} to ${next}`)
  return next            // becomes `prev` on the next run
}, 0)                    // ▲ initial prev
```

### Cleanup runs via `onCleanup`

To tear down a subscription/timer on re-run or disposal, call `onCleanup` inside the effect; it runs before the next execution and when the owner is disposed (→ [`05-lifecycle-and-ownership.md`](05-lifecycle-and-ownership.md)):

```ts
import { createEffect, onCleanup } from "solid-js"

createEffect(() => {
  const id = setInterval(() => console.log(tick()), 1000)
  onCleanup(() => clearInterval(id))   // runs on re-run and on dispose
})
```

> **Effects run only in the browser-ish runtime / on the client.** During SSR, `createEffect` does not run. Code that must produce a value usable on the server should be a memo or plain derivation, not an effect.

---

## `createEffect` to derive state is a code smell — use a memo

The most common Solid anti-pattern is mirroring one signal into another with an effect. It causes an extra update pass, can flash an intermediate state, and risks loops.

```ts
import { createSignal, createEffect, createMemo } from "solid-js"

const [items, setItems] = createSignal<number[]>([1, 2, 3, 4])

// ❌ effect-to-derive: a second signal kept in sync by an effect
const [evenCount, setEvenCount] = createSignal(0)
createEffect(() => {
  setEvenCount(items().filter(n => n % 2 === 0).length)
})
// Problems: extra signal + extra update tick; `evenCount()` is briefly stale after `items`
// changes but before the effect runs; trivially turns into a feedback loop if it reads itself.

// ✅ memo-to-derive: derived value, computed lazily, always consistent, one pass
const evenCount = createMemo(() => items().filter(n => n % 2 === 0).length)
// Read it the same way — evenCount() — but it's never out of sync and never loops.
```

**Rule of thumb:** if an effect's whole body is "compute a value from other signals and `setX(...)`," it should be a `createMemo` (or a plain accessor). Reserve `createEffect` for genuine side effects that reach *outside* the reactive graph.

---

## `createRenderEffect` and `createComputed` — the rare ones

Both look like `createEffect` but differ in **when they run**. The execution order on any update is:

```
createComputed  →  createRenderEffect  →  (render / DOM)  →  createEffect
   (pre-render)      (during render)                            (post-render)
```

### `createRenderEffect`

```ts
function createRenderEffect<T>(fn: (prev: T | undefined) => T, value?: T): void
```

Runs **during** the render phase, as DOM is being created (its first run is *before* the first `createEffect`). Reach for it only when a side effect must happen before paint — e.g. measuring or mutating a DOM node synchronously so the user never sees a flash. Most of the time `createEffect` is correct; render effects are an escape hatch.

### `createComputed`

```ts
function createComputed<T>(fn: (prev: T | undefined) => T, value?: T): void
```

Runs **immediately, before render**, and is intended for *writing to other reactive primitives* as part of the graph computation. It's the lowest-level effect and the easiest to misuse (it runs eagerly and synchronously, so a sloppy `createComputed` that writes signals can cascade). **Almost always you want a `createMemo` instead** — only reach for `createComputed` when you specifically need to push a value into another signal *synchronously before the render reads it*.

> **Default choice:** `createMemo` to derive, `createEffect` to side-effect. `createRenderEffect`/`createComputed` are specialist tools; if you're unsure which you need, you need neither.

---

## `on` — explicit dependencies and deferred first run

```ts
function on<S, T>(
  deps: Accessor<S> | AccessorArray<S>,
  fn: (input: S, prevInput: S | undefined, prev: T | undefined) => T,
  options?: { defer?: boolean }
): (prev: T | undefined) => T
```

`on` builds an effect/memo *body* that tracks **only** the `deps` you list — reads inside `fn` do **not** subscribe. You pass the result to `createEffect`/`createMemo`. The callback receives the dependency value(s), the previous dependency value(s), and the previous result.

```ts
import { createSignal, createEffect, on } from "solid-js"

const [a, setA] = createSignal(1)
const [b, setB] = createSignal(10)

createEffect(on(a, (aVal, prevA) => {
  // Re-runs ONLY when a() changes. Reading b() here does NOT subscribe to b.
  console.log(`a went ${prevA} → ${aVal}; b is currently ${b()}`)
}))

// Multiple deps as an array → callback receives arrays:
createEffect(on([a, b], ([aVal, bVal]) => {
  console.log("a or b changed:", aVal, bVal)
}))
```

### `defer: true` — skip the first run

By default the effect runs once immediately. `defer: true` makes it run **only on subsequent changes**, not on setup — the idiomatic "do something when X *changes*, but not on mount":

```ts
import { createSignal, createEffect, on } from "solid-js"

const [query, setQuery] = createSignal("")

createEffect(on(query, q => {
  void search(q)            // fires only when query() changes, not on initial mount
}, { defer: true }))
```

> **Why `on` over implicit tracking?** Two reasons: (1) you want a precise, fixed dependency set even though the body reads other signals, and (2) you want `defer`. If you don't need either, plain `createEffect(() => ...)` with auto-tracking is simpler.

---

## `untrack` — read without subscribing

```ts
function untrack<T>(fn: () => T): T
```

Inside a tracking scope, `untrack` runs `fn` *without* recording the signals it reads as dependencies. Use it to read a value you need but don't want to re-run on.

```ts
import { createSignal, createEffect, untrack } from "solid-js"

const [count, setCount] = createSignal(0)
const [factor, setFactor] = createSignal(2)

createEffect(() => {
  // Re-run when count() changes, but read factor() WITHOUT subscribing to it:
  const result = count() * untrack(factor)
  console.log(result)
})
// Changing factor() alone will NOT re-run this effect; changing count() will (and reads
// the latest factor at that moment).
```

> `on(deps, fn)` is essentially "track exactly `deps`, untrack the body." If you find yourself wrapping most of an effect in `untrack` and tracking one thing, reach for `on` instead — it's clearer.

---

## `batch` — coalesce multiple writes into one pass

```ts
function batch<T>(fn: () => T): T
```

Multiple synchronous writes normally each trigger an update pass. `batch` defers notification until `fn` returns, so observers see all the changes at once and run **once**.

```ts
import { createSignal, createEffect, batch } from "solid-js"

const [first, setFirst] = createSignal("Ada")
const [last, setLast] = createSignal("Lovelace")

createEffect(() => console.log(`${first()} ${last()}`))

batch(() => {
  setFirst("Grace")
  setLast("Hopper")
})   // effect logs ONCE → "Grace Hopper", not twice
```

> **Often you don't need it.** Solid already batches the writes made inside an event handler and inside effects. Reach for `batch` when you make several related writes from *plain* async/imperative code (a `setTimeout`, a network callback, a non-Solid event) and want them treated as one logical change.

---

## `createReaction` — one-shot "run once when X next changes"

```ts
function createReaction(onInvalidate: () => void): (tracking: () => void) => void
```

`createReaction` separates **tracking** from **execution**. It returns a `track` function; call `track(fn)` to record the dependencies read inside `fn`. The next time any of those change, `onInvalidate` fires **exactly once**, then the reaction goes dormant until you call `track` again.

```ts
import { createSignal, createReaction } from "solid-js"

const [value, setValue] = createSignal("start")

const track = createReaction(() => console.log("value changed (once)"))

// Arm it: record value() as the dependency
track(() => value())

setValue("end")     // → logs "value changed (once)"
setValue("final")   // → no-op; reaction is dormant until track() is called again
```

Use it for genuinely one-time reactions — "the first time this changes, do X and then stop watching." For "run on every change but not on mount," prefer `createEffect(on(dep, fn, { defer: true }))`, which is the more common pattern.

---

## The accessor-passing pattern

Because subscription is the *getter call inside a tracking scope*, the way you pass reactive state between functions/components determines whether it stays live. **Pass the accessor, not the value.**

```tsx
import { createSignal } from "solid-js"
import type { Accessor } from "solid-js"

function Parent() {
  const [count, setCount] = createSignal(0)

  // ❌ pass count() → the VALUE is read here, once, and frozen
  // <Display value={count()} />

  // ✅ pass count → the GETTER travels intact; Display reads it in its own tracking scope
  return <Display count={count} />
}

function Display(props: { count: Accessor<number> }) {
  // props.count is () => number; calling it inside JSX is the subscription
  return <span>{props.count()}</span>
}
```

The same applies to plain helper functions and to deriving on the way down — keep it a function:

```tsx
// ✅ derive lazily by passing an accessor, not a computed value
<Child label={() => `${count()} items`} />
```

> **Convention.** Local UI state is signals/stores passed as accessors like this; server state lives in Solid Query (whose `data` is itself reactive). You almost never read a signal into a `const` in a component body and pass that — that's the frozen-snapshot bug. (→ [`11-solid-query.md`](11-solid-query.md))

---

## Recipe: debouncing / throttling a signal

Solid has **no built-in debounce**. There are two shapes, and picking the wrong one is the usual bug.

**Debounce the *value*** when downstream consumers (a query key, a memo, a filter) should only see the settled value — this is what you want for search-as-you-type. Keep the raw signal bound to the input so typing stays responsive, and derive a lagging signal beside it:

```tsx
import { createSignal, createEffect, onCleanup } from "solid-js"

function createDebounced<T>(source: () => T, ms: number) {
  const [debounced, setDebounced] = createSignal(source())
  let timer: ReturnType<typeof setTimeout>
  createEffect(() => {
    const value = source()                       // tracked: re-runs per keystroke
    clearTimeout(timer)
    timer = setTimeout(() => setDebounced(() => value), ms)
  })
  onCleanup(() => clearTimeout(timer))
  return debounced
}

const [text, setText] = createSignal("")
const query = createDebounced(text, 300)

// input stays instant; only `query()` is delayed
<input value={text()} onInput={(e) => setText(e.currentTarget.value)} />
<Show when={query()}>{(q) => <Results for={q()} />}</Show>
```

**Debounce the *effect*** when the value should update immediately but the expensive work shouldn't run every time — autosave, analytics, resizing:

```tsx
createEffect(() => {
  const draft = text()                           // read synchronously → tracked
  const timer = setTimeout(() => save(draft), 500)
  onCleanup(() => clearTimeout(timer))           // cancels the previous pending run
})
```

> `onCleanup` **inside** an effect runs before each re-run, not just on unmount. That is what makes the second form a debounce at all — each new run cancels the timer the previous one scheduled.

For the maintained version, `@solid-primitives/scheduled` exports `debounce`, `throttle`, `scheduleIdle`, plus `leading`/`leadingAndTrailing` wrappers when you need the call to fire on the leading edge.

⚠️ Never debounce by reading the signal *after* an `await` or inside the `setTimeout` callback — the read leaves the tracking scope and the effect stops subscribing. → [Pitfalls #10](15-pitfalls.md)

---

## Recipe: persisting a signal to `localStorage`

Read once at creation (the body runs once — this is the correct place for a one-shot read), then write from an effect:

```tsx
import { createSignal, createEffect } from "solid-js"

function createPersisted<T>(key: string, fallback: T) {
  const stored = localStorage.getItem(key)
  const [value, setValue] = createSignal<T>(
    stored !== null ? (JSON.parse(stored) as T) : fallback,
  )
  createEffect(() => localStorage.setItem(key, JSON.stringify(value())))
  return [value, setValue] as const
}

const [theme, setTheme] = createPersisted("theme", "dark")
```

Notes that bite:

- **Writing is a side effect**, so it belongs in `createEffect`, never in a memo. → [The cardinal rules](#the-cardinal-rules)
- The initial `createEffect` run writes the fallback back to storage. Usually harmless; if you need to avoid it, use `on(value, …, { defer: true })`.
- `localStorage` is **synchronous and throws** when quota is exceeded or storage is blocked. Wrap the read in `try/catch` if the app must survive a corrupt entry.
- Cross-tab sync is not automatic — listen for the `storage` event and set the signal, with `onCleanup` to remove the listener.

`@solid-primitives/storage` (`makePersisted`) packages all of the above, including store support and cross-tab sync.

---

## The cardinal rules

1. **Reads must be inside a tracking scope to be reactive.** A read in the once-running component body, a plain event handler, a `setTimeout`, or inside `untrack` is a one-shot snapshot. (→ [`01-mental-model.md`](01-mental-model.md))
2. **Derive with a memo (or a plain accessor); side-effect with an effect.** If an effect's body is just "compute from signals and `setX(...)`," it's a memo in disguise — convert it.
3. **A memo is pure; an effect is impure.** Memos compute and return, nothing else. Effects reach outside the graph (DOM, network, storage) and clean up via `onCleanup`.
4. **Pass accessors, not values.** `count` keeps reactivity; `count()` freezes it. Same reason you never destructure props.
5. **Default to `createMemo`/`createEffect`.** `createComputed`/`createRenderEffect` are specialist; `on` is for explicit deps or `defer`; `batch` is for grouping out-of-band writes; `untrack` for surgical non-subscribing reads.

---

## See also

- [`01-mental-model.md`](01-mental-model.md) — why reads only react inside tracking scopes; the reactive graph
- [`03-components-and-props.md`](03-components-and-props.md) — props are live accessors; never destructure
- [`06-stores.md`](06-stores.md) — `createStore` for deep/structured reactive state (vs single-value signals)
- [`07-async-and-resources.md`](07-async-and-resources.md) — `createResource` for async-derived reactive state
- [`15-pitfalls.md`](15-pitfalls.md) — effect-as-derive, stale reads, and other reactivity bugs in depth
- Official docs: <https://docs.solidjs.com> (basic-reactivity & secondary-primitives reference)
