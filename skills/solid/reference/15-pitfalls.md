# Pitfalls & anti-patterns

> **When you reach for this:** something renders the *initial* value but never updates, an effect loops forever, a list re-creates everything (inputs lose focus), or a listener leaks. These are the real reactivity bugs Solid developers hit. Each one below is: **symptom → ❌ broken → ✅ fix → why** (one sentence on the mechanism). Find your symptom, apply the fix.

Almost every "it doesn't update" bug in Solid is the same root cause: **a reactive read happened outside a tracking scope, or the getter that carries the subscription was destroyed by destructuring.** Solid tracks *function calls in tracked scopes*, not values.

---

## Contents

- [Reactivity lost? Check these 5 things first](#reactivity-lost-check-these-5-things-first)
- [1. Destructuring props or store fields](#1-destructuring-props-or-store-fields)
- [2. Reading a signal in the component body](#2-reading-a-signal-in-the-component-body)
- [3. Early `return` of JSX based on a body-level signal read](#3-early-return-of-jsx-based-on-a-body-level-signal-read)
- [4. `.map()` instead of `<For>`, ternary instead of `<Show>`](#4-map-instead-of-for-ternary-instead-of-show)
- [5. `createEffect` used to derive or mirror state](#5-createeffect-used-to-derive-or-mirror-state)
- [6. Snapshotting a signal when passing it down](#6-snapshotting-a-signal-when-passing-it-down)
- [7. Stale closures: capturing `count()` in a callback created once](#7-stale-closures-capturing-count-in-a-callback-created-once)
- [8. `<For>` vs `<Index>` chosen wrong](#8-for-vs-index-chosen-wrong)
- [9. Mutating a store directly instead of using its setter](#9-mutating-a-store-directly-instead-of-using-its-setter)
- [10. `async` in `createEffect`: tracking lost after the first `await`](#10-async-in-createeffect-tracking-lost-after-the-first-await)
- [11. Forgetting `onCleanup` — leaked listeners, intervals, subscriptions](#11-forgetting-oncleanup-leaked-listeners-intervals-subscriptions)
- [12. Spreading props in a way that breaks reactivity](#12-spreading-props-in-a-way-that-breaks-reactivity)
- [13. Top-level signal reads in module scope (no owner)](#13-top-level-signal-reads-in-module-scope-no-owner)
- [14. Reading server state through effects instead of Solid Query](#14-reading-server-state-through-effects-instead-of-solid-query)
- [15. A new object replaced the one the store was tracking](#15-a-new-object-replaced-the-one-the-store-was-tracking)
- [16. Writing a signal from the component body or a memo](#16-writing-a-signal-from-the-component-body-or-a-memo)
- [17. `untrack` used to silence a bug instead of expressing intent](#17-untrack-used-to-silence-a-bug-instead-of-expressing-intent)
- [18. `<Show>`: static children vs the callback form, and `keyed`](#18-show-static-children-vs-the-callback-form-and-keyed)
- [Quick reference: symptom → cause](#quick-reference-symptom-cause)
- [See also](#see-also)


## Reactivity lost? Check these 5 things first

1. **Did you destructure props or a store?** `const { x } = props` / `{ x }` in params kills it. → [#1](#1-destructuring-props-or-store-fields)
2. **Did you read a signal in the component body** (not inside JSX/memo/effect)? Frozen snapshot. → [#2](#2-reading-a-signal-in-the-component-body)
3. **Is there an early `return` of JSX based on a signal read in the body?** It ran once. Use `<Show>`. → [#3](#3-early-return-of-jsx-based-on-a-body-level-signal-read)
4. **Did you use `.map()` or a ternary in JSX** instead of `<For>`/`<Show>`? → [#4](#4-map-instead-of-for-ternary-instead-of-show)
5. **Did you snapshot a signal when passing/reading it** — `count()` where you needed the accessor `count`, or read after an `await`? → [#6](#6-snapshotting-a-signal-when-passing-it-down) · [#10](#10-async-in-createeffect-tracking-lost-after-the-first-await)

Everything still updating, but **too much** of it? That's the identity family: a hand-built spread object ([#12](#12-spreading-props-in-a-way-that-breaks-reactivity)), a wholesale store replacement ([#15](#15-a-new-object-replaced-the-one-the-store-was-tracking)), or `<Show keyed>` ([#18](#18-show-static-children-vs-the-callback-form-and-keyed)).

---

## 1. Destructuring props or store fields

**Symptom:** the child shows the initial value but never updates when the parent changes it.

```tsx
// ❌ Each of these reads the proxy getter ONCE, at call time, and discards it.
function Name({ value }: { value: string }) { return <span>{value}</span> }
function Name(props: { value: string }) { const { value } = props; return <span>{value}</span> }
function Name(props: { value: string }) { const value = props.value; return <span>{value}</span> }
```

```tsx
// ✅ Read at the point of use; the getter re-runs on change.
function Name(props: { value: string }) {
  return <span>{props.value}</span>
}
// To "destructure" reactively, use splitProps / mergeProps (see chapter 03).
```

**Why:** props (and stores) are proxies whose getters *are* the subscription; destructuring invokes the getter once and stores a plain value, so nothing re-runs later. The same applies to `const { user } = store`.

---

## 2. Reading a signal in the component body

**Symptom:** a value computed in the body is stuck at its first value; the UI never reflects changes.

```tsx
// ❌ `label` is computed ONCE in the run-once body — frozen.
function Status(props: { online: () => boolean }) {
  const label = props.online() ? "Online" : "Offline"
  return <span>{label}</span>
}
```

```tsx
// ✅ Put the read inside a tracking scope: an inline accessor, a memo, or JSX.
function Status(props: { online: () => boolean }) {
  return <span>{props.online() ? "Online" : "Offline"}</span>
}
// or, if reused:
const label = createMemo(() => (props.online() ? "Online" : "Offline"))
```

**Why:** the component body runs exactly once; a read there captures a snapshot. Only JSX bindings, `createMemo`, `createEffect`, and other tracked scopes re-run when their dependencies change.

---

## 3. Early `return` of JSX based on a body-level signal read

**Symptom:** a "loading"/"empty" branch shows correctly at first but never switches to content (or vice-versa). Coming from React, you reach for an early return.

> Solid has **no rules-of-hooks** — you *can* call `createSignal`/`createMemo` conditionally or after a return. But conditional logic in the body still runs **once**. An early `return` chooses a branch one time and never re-evaluates.

```tsx
// ❌ The `if` runs once. If isLoading() is true at creation, you return the
//    spinner FOREVER — the body never re-runs to take the other branch.
function User(props: { isLoading: () => boolean; name: string }) {
  if (props.isLoading()) return <Spinner />
  return <h1>{props.name}</h1>
}
```

```tsx
// ✅ Express the branch as reactive control flow.
import { Show } from "solid-js"

function User(props: { isLoading: () => boolean; name: string }) {
  return (
    <Show when={!props.isLoading()} fallback={<Spinner />}>
      <h1>{props.name}</h1>
    </Show>
  )
}
```

**Why:** `<Show>` is a component that re-evaluates its `when` reactively and swaps the DOM; a top-level `if`/`return` is plain control flow evaluated a single time during the one component run.

---

## 4. `.map()` instead of `<For>`, ternary instead of `<Show>`

**Symptom:** the list doesn't update when items change, or it re-creates *every* row on any change (inputs lose focus, animations restart).

```tsx
// ❌ Runs once → never updates. Even if wrapped to update, it re-creates all rows.
<ul>{items().map((i) => <li>{i.name}</li>)}</ul>

// ❌ A ternary in JSX that flips on a signal re-creates the whole branch each time.
<div>{open() ? <Panel /> : null}</div>
```

```tsx
// ✅ <For> is keyed by item reference: only added/removed/moved rows touch the DOM.
import { For, Show } from "solid-js"

<ul><For each={items()}>{(i) => <li>{i.name}</li>}</For></ul>

// ✅ <Show> toggles without re-creating siblings.
<Show when={open()}><Panel /></Show>
```

**Why:** raw `.map()`/ternaries are evaluated as plain expressions and (when they do update) discard and rebuild DOM; `<For>` diffs by item identity and `<Show>` toggles a single boundary, preserving untouched nodes and their state. See [Control flow](04-control-flow.md).

---

## 5. `createEffect` used to derive or mirror state

**Symptom:** a signal that "shadows" another is always one tick behind, or you get an infinite loop / "too much recursion."

```tsx
// ❌ Mirroring one signal into another via an effect — extra signal, stale by a tick.
const [full, setFull] = createSignal("")
createEffect(() => setFull(`${first()} ${last()}`))

// ❌ Infinite loop: the effect reads `n` and writes `n`, re-triggering itself.
createEffect(() => setN(n() + 1))
```

```tsx
// ✅ Derived state is a memo (or a plain accessor). No extra signal, no lag.
const full = createMemo(() => `${first()} ${last()}`)
// usage: full()
```

**Why:** `createEffect` is for *side effects* (DOM, logging, network), not for computing values; `createMemo` caches a derived value and updates synchronously with its inputs. An effect that writes a signal it reads creates a feedback cycle. → [Reactivity](02-reactivity.md)

---

## 6. Snapshotting a signal when passing it down

**Symptom:** a child never reacts because you froze the value, *or* a child receives a getter it doesn't call.

```tsx
// ❌ Child destructures, so value={count()} is captured once → frozen.
function Display(props: { value: number }) {
  const { value } = props        // snapshot
  return <span>{value}</span>
}
<Display value={count()} />
```

```tsx
// ✅ Read props at point of use; the parent re-passes new values reactively.
function Display(props: { value: number }) {
  return <span>{props.value}</span>
}
<Display value={count()} />
```

The inverse — passing an **accessor** when the child expects a **value**:

```tsx
// ❌ Child reads props.value as a number, but you passed the function `count`.
<Display value={count} />        // props.value is () => number, renders "() => …"

// ✅ Pass the called value (parent JSX keeps it reactive), child reads props.value.
<Display value={count()} />
```

**Why:** `count()` in parent JSX is itself a tracked binding, so the parent re-evaluates and hands the child a fresh value on every change — the child only needs to read `props.value` in a tracked scope. Pass the bare accessor `count` only when the child must control *when* it reads. → [Components & props](03-components-and-props.md)

---

## 7. Stale closures: capturing `count()` in a callback created once

**Symptom:** an event handler, timer, or callback always sees the *original* value.

```tsx
// ❌ count() is read when the handler is CREATED (once) and baked in.
const value = count()
const onClick = () => console.log(value)    // always the first value

// ❌ Same: setInterval created in the run-once body captures the initial read.
const snapshot = count()
setInterval(() => doSomething(snapshot), 1000)
```

```tsx
// ✅ Read the signal INSIDE the callback so it reads current value each call.
const onClick = () => console.log(count())
setInterval(() => doSomething(count()), 1000)
```

**Why:** the component body runs once, so any value read there is captured by closure; calling the signal *inside* the callback reads the live value at call time (and outside a tracking scope it simply reads — it won't subscribe, which is what you want for a callback).

---

## 8. `<For>` vs `<Index>` chosen wrong

**Symptom:** with `<For>`, editing an input in a list jumps focus or shows the wrong row's value; or with `<Index>`, reordering doesn't visually move rows.

```tsx
// `<For each>` — keyed by item REFERENCE. Item is a value, index is a signal.
<For each={rows()}>{(row, i) => <Row data={row} n={i()} />}</For>

// `<Index each>` — keyed by POSITION. Index is a value, item is a SIGNAL.
<Index each={rows()}>{(row, i) => <Row data={row()} n={i} />}</Index>
```

**Rule of thumb:**

| Use | When |
| --- | --- |
| `<For>` | Items are objects with identity; the list is reordered/filtered; you want a row's DOM (and its input focus) to follow the item. |
| `<Index>` | Items are primitives, the list is a fixed/positional slot set, or each position holds form state that should stay put as values change. Editing a value shouldn't recreate the row. |

**Why:** `<For>` diffs by reference, so a new array of fresh objects (e.g. after a `.map()` that returns new objects) recreates every row; `<Index>` diffs by position and only updates the per-index signal. Picking by data identity vs positional identity avoids both focus loss and missed moves. → [Control flow](04-control-flow.md)

---

## 9. Mutating a store directly instead of using its setter

**Symptom:** you assign to a store property and nothing updates.

```tsx
const [state, setState] = createStore({ count: 0, user: { name: "a" } })

// ❌ Direct mutation bypasses the setter — no notification fires.
state.count = 1
state.user.name = "b"
```

```tsx
// ✅ Go through the setter (path syntax / function updater / produce).
setState("count", 1)
setState("user", "name", "b")
setState("count", (c) => c + 1)
import { produce } from "solid-js/store"
setState(produce((s) => { s.user.name = "b" }))
```

**Why:** the store proxy only emits change notifications when written through its setter; assigning to the proxy directly mutates the underlying object without telling subscribers. → [Stores](06-stores.md)

---

## 10. `async` in `createEffect`: tracking lost after the first `await`

**Symptom:** an async effect runs once but never re-runs when its signals change; or it keeps running stale fetches and writes results out of order.

```tsx
// ❌ Only reads BEFORE the first await are tracked. id() after await isn't
//    tracked, and there's no cancellation of the in-flight request.
createEffect(async () => {
  const a = await fetchThing(id())   // id() tracked here…
  setData(await enrich(a, other()))  // …other() read AFTER await: NOT tracked
})
```

```tsx
// ✅ For data fetching, use createResource (handles tracking + Suspense + races).
import { createResource } from "solid-js"
const [data] = createResource(id, (id) => fetchThing(id))

// ✅ If you must use an effect, read deps synchronously and add cleanup.
createEffect(() => {
  const currentId = id()             // read synchronously → tracked
  let cancelled = false
  fetchThing(currentId).then((r) => { if (!cancelled) setData(r) })
  onCleanup(() => { cancelled = true })
})
```

**Why:** Solid's tracking only captures signal reads during the **synchronous** portion of the computation; after an `await`, the effect resumes outside the tracking context, so those reads neither subscribe nor cancel the previous run. → [Async & resources](07-async-and-resources.md)

---

## 11. Forgetting `onCleanup` — leaked listeners, intervals, subscriptions

**Symptom:** intervals keep firing after the component is gone; duplicate event handlers stack up; memory grows.

```tsx
// ❌ Never cleaned up — the interval outlives the component.
function Clock() {
  const [t, setT] = createSignal(Date.now())
  setInterval(() => setT(Date.now()), 1000)   // leaks
  return <span>{t()}</span>
}
```

```tsx
// ✅ Register cleanup; it runs on unmount (and before an owner re-run).
import { onCleanup } from "solid-js"

function Clock() {
  const [t, setT] = createSignal(Date.now())
  const id = setInterval(() => setT(Date.now()), 1000)
  onCleanup(() => clearInterval(id))
  return <span>{t()}</span>
}
```

**Why:** `onCleanup` registers a disposer on the current reactive owner; when that owner is disposed (component unmount) the disposer runs. Without it, timers/listeners are never released. → [Lifecycle & ownership](05-lifecycle-and-ownership.md)

---

## 12. Spreading props in a way that breaks reactivity

**Symptom:** forwarded attributes don't update, or you accidentally read a getter twice.

```tsx
// ❌ Building a new object of snapshots, then spreading it — frozen.
const forwarded = { ...props, class: cn(props.class) }
return <input {...forwarded} />
```

```tsx
// ✅ Split, then spread the rest PROXY Solid gives you (stays reactive).
import { splitProps } from "solid-js"
const [local, rest] = splitProps(props, ["class"])
return <input class={cn(local.class)} {...rest} />
```

**Why:** spreading a Solid proxy (`rest` from `splitProps`, or a `mergeProps` result) is compiled to reactive per-key reads; spreading a hand-built object evaluates each key once. → [Components & props](03-components-and-props.md)

---

## 13. Top-level signal reads in module scope (no owner)

**Symptom:** a signal/effect/memo created at module top level warns "computations created outside a `createRoot` or `render` will never be disposed," or cleanup never runs.

```tsx
// ❌ No owner: this effect can never be disposed, and onCleanup never fires.
const [count, setCount] = createSignal(0)
createEffect(() => console.log(count()))   // module scope — leaks
```

```tsx
// ✅ Give it an owner with createRoot (you control disposal).
import { createRoot } from "solid-js"

const dispose = createRoot((dispose) => {
  const [count, setCount] = createSignal(0)
  createEffect(() => console.log(count()))
  return dispose
})
// later: dispose()
```

**Why:** reactive computations live under an *owner* (created by `render`/`createRoot`/a parent component); without one there's nothing to track lifetime or run cleanup. Inside components you already have an owner — this only bites code that runs at import time. → [Lifecycle & ownership](05-lifecycle-and-ownership.md)

---

## 14. Reading server state through effects instead of Solid Query

**Symptom (the reference app):** hand-rolled `createEffect` + `createSignal` caching that goes stale, double-fetches, or races — reinventing what the query layer already does.

```tsx
// ❌ Manual cache/refetch/loading in effects — fragile, no dedupe or invalidation.
const [user, setUser] = createSignal<User>()
createEffect(() => { fetchUser(id()).then(setUser) })
```

```tsx
// ✅ Server state is Solid Query; options go in a FUNCTION so they stay reactive.
import { createQuery } from "@tanstack/solid-query"
const userQuery = createQuery(() => ({
  queryKey: ["user", id()],
  queryFn: () => fetchUser(id()),
}))
// userQuery.data, .isPending, .error — caching/refetch/invalidation handled.
```

**Why:** Solid Query owns caching, deduping, refetching and invalidation; the **options-function** idiom (`createQuery(() => ({...}))`) is what keeps the key reactive so the query re-runs when `id()` changes. Local UI state stays in signals/stores; server state does not belong in effects. → [Solid Query](11-solid-query.md) · [Architecture](16-architecture.md)

---

## 15. A new object replaced the one the store was tracking

**Symptom:** you refetch or re-assign a slice of a store and *everything* under it re-renders — lists rebuild, inputs lose focus, `<For>` rows are all new — even though most of the data is identical. The inverse of #9: the setter *was* used, so the write lands, but it lands as a wholesale replacement.

```tsx
// ❌ Replaces the whole array with fresh object references. Every row is "new"
//    to <For>, so every row's DOM is torn down and rebuilt.
const fresh = await fetchTodos()
setState("todos", fresh)
```

```tsx
// ✅ reconcile diffs the incoming data against what's there and writes only the
//    leaves that actually differ, preserving identity for unchanged items.
import { reconcile } from "solid-js/store"

const fresh = await fetchTodos()
setState("todos", reconcile(fresh, { key: "id" }))
```

**Why:** store reactivity is per-property, and `<For>` keys by object reference. Assigning a freshly-deserialized array swaps every reference at once, so both the property subscriptions and the list keys see a total change. `reconcile` walks the new value and applies a minimal diff, matching items by `key` (default `"id"`); unchanged items keep their identity. Use it for **any** data arriving from outside — fetch, SSE, `JSON.parse`, IPC. → [Stores](06-stores.md)

---

## 16. Writing a signal from the component body or a memo

**Symptom:** a "computations created outside…" or out-of-order-update warning, a value that lags one render behind, or an update that silently doesn't propagate.

```tsx
// ❌ Writing during the run-once body — the write races the initial render and
//    is invisible to anything that already read the signal.
function Panel(props: { items: Item[] }) {
  setCount(props.items.length)      // side effect in the body
  return <span>{count()}</span>
}

// ❌ A memo must be PURE. Writing another signal from inside one makes the
//    graph's update order undefined.
const total = createMemo(() => { setDirty(true); return a() + b() })
```

```tsx
// ✅ If it's derived, derive it — no second signal exists to get out of sync.
const count = () => props.items.length

// ✅ If it genuinely is a side effect, it belongs in an effect, which runs
//    after render and is allowed to write.
createEffect(() => setDirty(a() + b() > 0))
```

**Why:** the body and memos run *during* graph construction/evaluation, where Solid assumes reads are pure. Writes there either land before subscribers exist or reorder the update pass. Reads happen anywhere; **writes belong in event handlers and effects**. → [Reactivity](02-reactivity.md)

---

## 17. `untrack` used to silence a bug instead of expressing intent

**Symptom:** you wrapped something in `untrack` to stop an effect looping or re-running, and now it doesn't update when it genuinely should.

```tsx
// ❌ untrack around the whole body: the effect now has NO dependencies and
//    runs exactly once. It "stopped looping" because it stopped working.
createEffect(() => untrack(() => { save(draft(), userId()) }))
```

```tsx
// ✅ Say which value is the trigger and which is merely read.
//    Re-runs when draft() changes; reads the current userId() without
//    subscribing to it.
createEffect(on(draft, (d) => save(d, untrack(userId))))
```

**Why:** `untrack` is not "make this stop re-running" — it is "read this value without subscribing to it." Untracking the trigger as well as the incidental read leaves a computation with an empty dependency set. When you want *explicit* dependencies, reach for `on(deps, fn)` (add `{ defer: true }` to skip the initial run) and untrack only the incidental reads inside. → [Reactivity](02-reactivity.md)

---

## 18. `<Show>`: static children vs the callback form, and `keyed`

**Symptom:** TypeScript insists `when` might be `null` inside the block; or the whole subtree is rebuilt every time `when` changes value rather than truthiness.

```tsx
// ❌ Rebuilds the entire subtree whenever user() changes identity, not just
//    when it flips between present and absent.
<Show when={user()} keyed>{(u) => <Profile user={u} />}</Show>
```

```tsx
// ✅ Callback children narrow the type without keying: the block is created
//    once on truthy and `u` is an ACCESSOR that stays live.
<Show when={user()}>{(u) => <Profile user={u()} />}</Show>

// ✅ Static children are fine when you don't need the narrowed value.
<Show when={isOpen()}><Panel /></Show>
```

**Why:** plain `<Show>` toggles on **truthiness** and reuses the DOM subtree; the callback receives an accessor so the value stays reactive. Adding `keyed` changes the identity semantics — the block is torn down and recreated whenever `when` changes *value*, and the callback then receives a plain value instead of an accessor. Use `keyed` only when you genuinely want a fresh subtree per value (resetting local state deliberately). → [Control flow](04-control-flow.md) · [Performance](12-performance.md)

---

## Quick reference: symptom → cause

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Child shows initial value, never updates | Destructured props/store | Read `props.x`; `splitProps`/`mergeProps` (#1) |
| Child frozen although you passed `count()` | Snapshot taken in the child | Read `props.value` at point of use (#6) |
| Body-computed value frozen | Read in run-once body | Move read into JSX/memo (#2) |
| Branch never switches | Early `return` on a signal | `<Show>` (#3) |
| List doesn't update / rebuilds all rows | `.map()`/ternary in JSX | `<For>`/`<Show>` (#4) |
| Shadow signal lags / infinite loop | `createEffect` deriving state | `createMemo` (#5) |
| Callback sees old value | Stale closure over `x()` | Read `x()` inside the callback (#7) |
| Input loses focus on list change | `<For>` vs `<Index>` mismatch | Pick by identity (#8) |
| Store write does nothing | Direct mutation | Use the setter / `produce` (#9) |
| Async effect runs once / races | Tracking lost after `await` | `createResource` / sync read + cleanup (#10) |
| Timer/listener keeps firing | Missing `onCleanup` | Register cleanup (#11) |
| Module-scope warning, no disposal | No owner | `createRoot` (#13) |
| Forwarded attributes don't update | Hand-built spread object | Spread the `splitProps` proxy (#12) |
| Hand-rolled cache goes stale / double-fetches | Server state in effects | Solid Query (#14) |
| Whole list rebuilds after a refetch | New object refs replaced the tracked ones | `reconcile(data, { key: "id" })` (#15) |
| Value lags a render / undefined update order | Signal written from the body or a memo | Derive it, or write from an effect (#16) |
| Effect stopped looping *and* stopped working | `untrack` swallowed the trigger | `on(deps, fn)` + untrack only incidental reads (#17) |
| Subtree rebuilt on every value change | `<Show keyed>` | Drop `keyed`; use the accessor callback (#18) |

## See also

- [Components & props](03-components-and-props.md) — the destructuring rule in depth, prop helpers
- [Reactivity](02-reactivity.md) — signals/memos/effects, tracking scopes, `untrack`/`batch`/`on`
- [Control flow](04-control-flow.md) — `<Show>`/`<For>`/`<Index>`/`<Switch>` and For-vs-Index
- [Lifecycle & ownership](05-lifecycle-and-ownership.md) — owners, `onCleanup`, `createRoot`
- [Async & resources](07-async-and-resources.md) · [Stores](06-stores.md) · [Solid Query](11-solid-query.md)
