# Performance

> **When you reach for this:** when something feels slow, when lists flicker or re-create unexpectedly, when you're reaching for "memoisation" but aren't sure what you're actually optimising.

Solid's performance story is the inverse of React's. Because there is no virtual DOM and no component re-render, the normal React toolkit — `React.memo`, `useCallback`, `useMemo` to avoid re-renders — simply does not apply. In Solid, **work only happens inside reactive computations that read a changed signal.** The component function itself is off the critical path entirely; it ran once at mount and is done.

That means performance in Solid is really two questions:
1. Are my reactions too wide — doing more work than the changed value warrants?
2. Am I accidentally creating or destroying DOM nodes when I should be reusing them?

---

## Contents

- [Where work actually happens](#where-work-actually-happens)
- [`<For>` vs `<Index>`: list reconciliation](#for-vs-index-list-reconciliation)
- [`<Show>` and accidental DOM recreation](#show-and-accidental-dom-recreation)
- [Keeping reactions narrow](#keeping-reactions-narrow)
- [Avoiding expensive work in tracked scopes](#avoiding-expensive-work-in-tracked-scopes)
- [Large lists: virtualization](#large-lists-virtualization)
- [Lazy loading and code splitting](#lazy-loading-and-code-splitting)
- [Performance checklist](#performance-checklist)
- [See also](#see-also)


## Where work actually happens

The reactive graph is a directed graph of **signals → computations**. When a signal changes, only the computations that subscribed to it are re-run. A computation is anything created by `createEffect`, `createMemo`, a JSX binding (`{value()}`), or an attribute (`class={...}`).

```tsx
import { createSignal, createMemo, createEffect } from "solid-js"

function Widget() {
  const [a, setA] = createSignal(0)
  const [b, setB] = createSignal(0)

  // Only re-runs when `a` changes, never when `b` changes
  const doubled = createMemo(() => a() * 2)

  // Only re-runs when `b` changes
  createEffect(() => console.log("b changed:", b()))

  return (
    <div>
      {/* Only this text node updates when doubled() changes */}
      <p>{doubled()}</p>
      {/* This text node is independent — it updates only when b() changes */}
      <p>{b()}</p>
    </div>
  )
}
```

When `setA(1)` is called: the `doubled` memo re-runs, which propagates to the `{doubled()}` text binding. The `b` effect and `{b()}` binding do not execute at all.

> **`createMemo` is not `React.memo`.** It does not prevent component re-renders (there are none). It caches an **expensive derivation** or **stabilises object identity** so that downstream computations that compare by reference don't spuriously re-run. Only reach for it when the computation inside is genuinely expensive, or when multiple downstream computations share the same derived value.

---

## `<For>` vs `<Index>`: list reconciliation

These two components handle lists differently and the choice has correctness and performance implications.

### `<For>`: keyed by reference (items as signals)

```tsx
import { For } from "solid-js"

// Each row is keyed to a stable item reference.
// The index is a signal (can change without recreating the row).
// The item value itself is not a signal (it's the stable key).
<For each={items()}>
  {(item, index) => (
    <li>{item.name} — position: {index()}</li>
  )}
</For>
```

- The callback fires once per item. The row DOM is created once and reused.
- When an item moves in the array (sort/reorder), Solid moves the existing DOM node; it does **not** destroy and recreate it.
- `index` is a reactive accessor `() => number` because position can change while the item stays stable.
- Best for arrays of objects with stable identity.

### `<Index>`: keyed by position (items as signals)

```tsx
import { Index } from "solid-js"

// Each row is keyed to a stable index position.
// The item value at that position is a signal (can change without recreating the row).
<Index each={items()}>
  {(item, index) => (
    <li>{item()}</li>
  )}
</Index>
```

- The callback fires once per position. Rows are never recreated unless the list grows or shrinks.
- `item` is a reactive accessor `() => T` because the value at each position can change.
- When the array changes content at a stable length (e.g., updating primitives in place), no rows are destroyed.
- Best for **large arrays of primitives** (strings, numbers) or any list with a stable length and changing content.

| | `<For>` | `<Index>` |
|---|---|---|
| Row identity | item reference | position |
| item arg | `T` (stable) | `() => T` (reactive) |
| index arg | `() => number` (reactive) | `number` (stable) |
| Re-order cost | moves DOM, no recreation | recreates all changed positions |
| Content-change cost | no change | updates only changed positions |
| Best for | objects with stable identity | primitives, fixed-length lists |

❌ Don't use `.map()` directly in JSX for dynamic lists:
```tsx
// ❌ .map() runs in a tracked scope during initial render but is NOT reactive.
// The list will not update when items() changes.
<ul>{items().map(item => <li>{item.name}</li>)}</ul>

// ✅ Use <For> — it tracks the signal and reconciles efficiently.
<ul>
  <For each={items()}>{item => <li>{item.name}</li>}</For>
</ul>
```

---

## `<Show>` and accidental DOM recreation

`<Show>` has two modes and they have very different performance characteristics.

### Plain `<Show>` — reuses the DOM subtree

```tsx
import { Show } from "solid-js"

// The child is created once when `when` first becomes truthy.
// When `when` changes between truthy values, the DOM is REUSED.
<Show when={user()}>
  {/* This subtree is created once; not recreated on user() changes */}
  <Profile name={user()!.name} />
</Show>
```

The child callback receives a plain value (not a signal) of `T` — the non-nullable form when `when` is truthy. Solid exposes it as a function child:

```tsx
<Show when={user()}>
  {(u) => <Profile name={u().name} />}
  {/* u is an Accessor<NonNullable<T>> so you get narrowed type */}
</Show>
```

### `<Show keyed>` — recreates the DOM on value change

```tsx
// keyed={true}: Solid tears down and rebuilds the subtree every time
// the `when` value changes, even between two truthy values.
<Show when={selectedTab()} keyed>
  {(tab) => <TabPanel tab={tab} />}
</Show>
```

Use `keyed` when you need a **fresh DOM + fresh state** for each distinct value — for example, a panel component with internal state that should reset when the selected tab changes. Avoid it otherwise: every truthy change is a full destroy + recreate cycle.

| | `<Show>` | `<Show keyed>` |
|---|---|---|
| Subtree lifecycle | created once, hidden/shown | recreated on every value change |
| Child arg type | `T \| null \| undefined` (accessor in callback form) | `NonNullable<T>` (narrowed) |
| Cost on change | none (DOM reuse) | full destroy + mount |
| Use when | condition toggle | identity change requires fresh state |

---

## Keeping reactions narrow

**The golden rule:** a reactive computation should read only the signals it genuinely needs to update its output.

> **Selection in a long list is the classic O(n) trap.** If every row reads `selectedId()` to decide whether it is highlighted, changing the selection re-runs *every* row. `createSelector` turns that into two updates — the row losing selection and the row gaining it — regardless of list length. It is documented in [Async & resources § `createSelector`](07-async-and-resources.md); reach for it here.

### Avoid reading signals inside effects unnecessarily

```tsx
import { createSignal, createEffect, createMemo } from "solid-js"

const [items, setItems] = createSignal<string[]>([])
const [filter, setFilter] = createSignal("")

// ❌ This effect re-runs when EITHER items OR filter changes, even if
// the expensive work only depends on one.
createEffect(() => {
  const count = items().filter(i => i.includes(filter())).length
  document.title = `${count} results`
})

// ✅ Derive first, effect just reads the already-computed value.
const count = createMemo(() =>
  items().filter(i => i.includes(filter())).length
)
createEffect(() => {
  document.title = `${count()} results`
})
```

When multiple consumers share the same derived value, a single `createMemo` computes it once. Without it, each consumer re-derives it independently every time.

### `untrack`: opt out of tracking for a specific read

```tsx
import { createSignal, createEffect, untrack } from "solid-js"

const [a, setA] = createSignal(0)
const [b, setB] = createSignal(0)

// Re-runs only when `a` changes. Reading `b` inside untrack
// does not create a subscription to `b`.
createEffect(() => {
  const aVal = a()
  const bVal = untrack(b)   // read b without subscribing
  console.log(aVal, bVal)
})
```

`untrack` is the escape hatch for: "I need to read this value at reaction time, but I don't want this reaction to be scheduled when it changes."

### `batch`: defer signal notifications until a block completes

```tsx
import { createSignal, batch } from "solid-js"

const [x, setX] = createSignal(0)
const [y, setY] = createSignal(0)

// ❌ Two separate notifications; any computation reading both will run twice.
setX(1)
setY(2)

// ✅ One notification; computations reading x or y run once after both update.
batch(() => {
  setX(1)
  setY(2)
})
```

Solid already batches effects scheduled within event handlers in the browser (because the event handler is a synchronous call), so explicit `batch` is most useful in async contexts or when triggering multiple store mutations from a utility function.

### `on`: explicit dependency declaration with optional deferral

```tsx
import { createSignal, createEffect, on } from "solid-js"

const [source, setSource] = createSignal(0)
const [other, setOther] = createSignal("x")

// Explicitly tracks only `source`; `other` reads inside the callback
// do not create subscriptions even without untrack.
createEffect(on(source, (val) => {
  console.log("source changed to", val)
}))

// defer: true — skip the initial run; only fire on subsequent changes.
createEffect(on(source, (val) => {
  console.log("source changed after mount:", val)
}, { defer: true }))
```

`on` accepts a single dependency or an array of dependencies. It's the recommended pattern when you want Vue-`watch`-style explicit dependencies.

---

## Avoiding expensive work in tracked scopes

JSX in Solid runs **once** during component setup, inside a tracking scope. Work that happens inline during that initial pass is synchronous and runs during the render. Keep it cheap or push it into a `createMemo`.

```tsx
// ❌ Expensive sort runs every time this memo is evaluated.
// This is fine if sortedItems is a memo, but if it's inline in JSX:
<For each={items().sort(comparator)}>
  ...
</For>
// The sort() runs in the JSX expression during render.

// ✅ Memoize expensive derivations.
const sorted = createMemo(() => [...items()].sort(comparator))

<For each={sorted()}>
  ...
</For>
// Now the sort only re-runs when items() changes, not every time
// the parent expression evaluates.
```

> Note: sorting mutates the original array. Always `[...spread]` before sorting in Solid.

---

## Large lists: virtualization

For lists with hundreds or thousands of rows, mount only what the user can see. `@tanstack/solid-virtual` is the standard choice — it's headless (no DOM, no styles) and integrates directly with Solid's reactivity.

```tsx
import { createVirtualizer } from "@tanstack/solid-virtual"
import { createSignal, For } from "solid-js"

function BigList(props: { items: string[] }) {
  let containerEl: HTMLDivElement | undefined

  const virtualizer = createVirtualizer({
    count: props.items.length,
    getScrollElement: () => containerEl!,
    estimateSize: () => 36,    // row height estimate in px
    overscan: 5,
  })

  return (
    <div ref={containerEl} style={{ height: "400px", overflow: "auto" }}>
      <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
        <For each={virtualizer.getVirtualItems()}>
          {(virtualRow) => (
            <div
              style={{
                position: "absolute",
                top: `${virtualRow.start}px`,
                height: `${virtualRow.size}px`,
                width: "100%",
              }}
            >
              {props.items[virtualRow.index]}
            </div>
          )}
        </For>
      </div>
    </div>
  )
}
```

For long **primitive** lists (e.g., log lines, autocomplete candidates), `<Index>` combined with virtualization is a natural pairing: `<Index>` minimises row recreation, virtualisation limits total mounted rows.

---

## Lazy loading and code splitting

Route components that are large or rarely accessed should be code-split. Solid's `lazy()` wraps a dynamic `import()` and returns a component. Pair it with `<Suspense>` to render a fallback while the chunk loads.

```tsx
import { lazy, Suspense } from "solid-js"
import { Route, Router } from "@solidjs/router"

const Settings = lazy(() => import("./pages/Settings"))
const Dashboard = lazy(() => import("./pages/Dashboard"))

function App() {
  return (
    <Router>
      <Suspense fallback={<p>Loading…</p>}>
        <Route path="/settings" component={Settings} />
        <Route path="/dashboard" component={Dashboard} />
      </Suspense>
    </Router>
  )
}
```

`lazy()` accepts any `() => Promise<{ default: Component }>`. The imported module must have a **default export** that is a Solid component. Wrap `<Suspense>` high enough that navigation between lazy routes shows a sensible fallback without nesting multiple boundaries unnecessarily.

You can also preload on hover/focus:

```tsx
const Settings = lazy(() => import("./pages/Settings"))

// Preload before the user actually navigates
<button onMouseEnter={() => Settings.preload()}>
  Go to Settings
</button>
```

---

## Performance checklist

When something is slow or the DOM is doing more work than expected, work through these in order:

| Check | What to look for |
|---|---|
| **`.map()` instead of `<For>`** | Static snapshot, not reactive; list never updates |
| **Signal created inside render** | A `createSignal` call in JSX (not in component body) creates a new signal on every update cycle |
| **Expensive work inline in JSX** | Sorts, filters, JSON parsing in JSX expressions run on the initial pass; memoize them |
| **`<Show keyed>` on a fast-changing value** | Constant DOM destroy + recreate; remove `keyed` or reconsider the structure |
| **`createEffect` reading too many signals** | Effect re-runs more than the output change warrants; derive with `createMemo` first |
| **Missing `lazy()` boundary on large routes** | Entire app JS is parsed before first paint; split by route |
| **Large flat list without virtualization** | Thousands of DOM nodes; introduce `@tanstack/solid-virtual` |
| **`<Index>` vs `<For>` mismatch** | Objects with `<Index>` lose stable identity; primitives with `<For>` cause unnecessary reconciliation |
| **`batch` missing in async code** | Multiple `setX` calls outside an event handler each notify separately |

---

## See also

- [Mental model](01-mental-model.md) — why there are no re-renders to optimise
- [Reactivity](02-reactivity.md) — `createMemo`, `createEffect`, `untrack`, `batch` in depth
- [Components and props](03-components-and-props.md) — `<For>`, `<Index>`, `<Show>`, `<Suspense>`, `lazy`
