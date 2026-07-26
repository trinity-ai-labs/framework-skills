# Lifecycle & Ownership

How Solid components start, how they clean up after themselves, and the reactive tree that makes auto-disposal possible. The ownership model is what separates Solid's memory management from "remember to unsubscribe everywhere" — once you understand it, `onCleanup` and `createRoot` snap into place.

Verified against **solid-js v1.9.x** (`packages/solid/src/reactive/signal.ts`).

---

## Contents

- [The one-sentence lifecycle](#the-one-sentence-lifecycle)
- [`onMount`](#onmount)
- [`onCleanup`](#oncleanup)
- [Ownership — the reactive tree](#ownership-the-reactive-tree)
- [`getOwner` and `runWithOwner`](#getowner-and-runwithowner)
- [`createRoot`](#createroot)
- [`createUniqueId`](#createuniqueid)
- [`render` — the entry point](#render-the-entry-point)
- [The full interplay](#the-full-interplay)
- [Common patterns](#common-patterns)
- [Cheat sheet](#cheat-sheet)
- [See also](#see-also)


## The one-sentence lifecycle

> **Component body → first render → `onMount` callbacks → reactive updates (via effects) → `onCleanup` → disposal.**

Components run their body once as a factory (see [01-mental-model.md](01-mental-model.md)). That factory registers signals, effects, cleanup hooks, and child components. When the component is removed from the tree, Solid disposes its reactive owner, which triggers every registered cleanup in reverse order. There is no componentDidUpdate — reactive effects handle incremental updates.

---

## `onMount`

```ts
import { onMount } from "solid-js"

function onMount(fn: () => void): void
```

Runs `fn` **once**, after the component's DOM has been inserted into the document.

Internally it is:

```ts
export function onMount(fn: () => void) {
  createEffect(() => untrack(fn))
}
```

That is all it is: a `createEffect` whose callback is wrapped in `untrack`. Because `fn` reads no signals (untrack suppresses subscription), the effect never has a reason to re-run. The deferred scheduling of `createEffect` ensures the DOM is committed before `fn` executes.

### What it is for

| Use `onMount` for | Don't use `onMount` for |
|---|---|
| Measuring DOM geometry | Fetching data (use `createResource` / `useQuery`) |
| Setting focus on an input | Computing derived state |
| Attaching third-party widgets | Subscriptions that must track signals |
| Kicking off non-reactive setup (analytics, observers) | Side effects that should re-run when signals change |

```tsx
import { createSignal, onMount } from "solid-js"

function AutoFocusInput() {
  let inputRef!: HTMLInputElement

  onMount(() => {
    inputRef.focus()
  })

  return <input ref={inputRef} />
}
```

> **SSR note.** `createEffect` (and therefore `onMount`) is a no-op on the server. Browser-only setup belongs in `onMount` — it never fires during SSR and never causes hydration mismatches.

### `onMount` does not re-run

```tsx
import { createSignal, onMount } from "solid-js"

function Example() {
  const [count, setCount] = createSignal(0)

  onMount(() => {
    // ✅ runs exactly once after initial render
    // ❌ does NOT re-run when count() changes — fn is untracked
    console.log("mounted, count at mount time:", count())
  })

  return <button onClick={() => setCount(c => c + 1)}>{count()}</button>
}
```

If you need to respond to signal changes, use `createEffect`, not `onMount`.

---

## `onCleanup`

```ts
import { onCleanup } from "solid-js"

function onCleanup<T extends () => any>(fn: T): T
```

Registers a cleanup function on the **current reactive owner**. Returns the same `fn` so you can write `const cancel = onCleanup(myFn)` and invoke it manually if needed.

The cleanup runs:
- **Inside a `createEffect`:** before the effect re-runs (each time its tracked dependencies change), and when the owner is finally disposed.
- **At component top level:** once, when the component is unmounted.

### `onCleanup` inside `createEffect`

```tsx
import { createSignal, createEffect, onCleanup } from "solid-js"

function PointerTracker() {
  const [target, setTarget] = createSignal<string | null>(null)

  createEffect(() => {
    const id = target()   // tracked — effect re-runs when target changes
    if (!id) return

    const el = document.getElementById(id)
    if (!el) return

    const handler = (e: PointerEvent) => console.log(id, e.clientX, e.clientY)
    el.addEventListener("pointermove", handler)

    // ✅ runs BEFORE the next re-run (when target changes) AND on unmount
    onCleanup(() => el.removeEventListener("pointermove", handler))
  })

  return (
    <select onChange={e => setTarget(e.currentTarget.value)}>
      <option value="">none</option>
      <option value="box">box</option>
    </select>
  )
}
```

Each time `target()` changes, Solid re-runs the effect. Before it does, it fires the previously registered `onCleanup` — removing the old listener — then the effect body runs again and attaches a fresh listener to the new element. No stale listeners accumulate.

### `onCleanup` at component top level

```tsx
import { onCleanup } from "solid-js"

function Clock() {
  const [time, setTime] = createSignal(new Date())

  // Interval set up once; cleanup runs once on unmount
  const id = setInterval(() => setTime(new Date()), 1000)
  onCleanup(() => clearInterval(id))

  return <p>{time().toLocaleTimeString()}</p>
}
```

### The "outside a reactive scope" warning

```ts
// ❌ In dev, logs: "cleanups created outside a `createRoot` or `render` will never be run"
// In production: silently does nothing
onCleanup(() => console.log("this never fires"))
```

If you see this warning, the call site is not inside any reactive owner. Wrap it in a `createRoot`, a component, or an effect.

---

## Ownership — the reactive tree

Every reactive computation in Solid (effects, memos, the component body itself, resources) has an **owner** — a node in an internal tree. When an owner is disposed, Solid:

1. Disposes all child computations it owns.
2. Runs all registered cleanup functions (`onCleanup`) in reverse registration order.

This is automatic. You do not need to unsubscribe from signals manually — subscriptions are tracked by the reactive graph, and when the owning computation is disposed, those subscriptions are removed. The tree structure means you can create nested reactive scopes and trust that disposing a parent cascades cleanly to all children.

```
App (root owner)
├── <Header> (owned computation)
│   └── createEffect (child of Header's owner)
│       └── onCleanup registered here
└── <Main> (owned computation)
    ├── <Sidebar> (child owner)
    └── createEffect
```

When `<Sidebar>` unmounts, only Sidebar's subtree is disposed — App, Header, and Main are untouched.

---

## `getOwner` and `runWithOwner`

```ts
import { getOwner, runWithOwner } from "solid-js"

function getOwner(): Owner | null
function runWithOwner<T>(owner: Owner | null, fn: () => T): T | undefined
```

### Why you need them

Reactive computations created inside a synchronous owner (a component, an effect) inherit that owner automatically. But the moment you cross an async boundary — an `await`, a `Promise.then`, a `setTimeout` — you lose the owner:

```ts
import { createSignal, getOwner, runWithOwner, createEffect } from "solid-js"

function BadExample() {
  const [x, setX] = createSignal(0)

  // ❌ The async callback runs outside the component's owner
  fetch("/api/data").then(() => {
    createEffect(() => console.log(x()))
    // Warning: computations created outside a `createRoot` or owner...
  })
}
```

`getOwner` captures the owner at the synchronous call site. `runWithOwner` re-establishes it when the async code runs:

```ts
import { createSignal, getOwner, runWithOwner, createEffect, onCleanup } from "solid-js"

function GoodExample() {
  const [x, setX] = createSignal(0)
  const owner = getOwner()

  fetch("/api/data").then(() => {
    // ✅ re-establishes the component's owner for the async callback
    runWithOwner(owner, () => {
      createEffect(() => console.log(x()))
      // onCleanup works here too — it registers on the component's owner
      onCleanup(() => console.log("cleaned up"))
    })
  })
}
```

### What `runWithOwner` does (and does not)

- Sets `Owner` to the captured owner while `fn` runs.
- Sets `Listener` to `null` — **signals read inside `fn` are not tracked**. Reactivity only happens naturally inside reactive computations created by `fn`, not from the `runWithOwner` call itself.
- Returns `T | undefined` — errors thrown by `fn` are passed to the owner's error handler; `undefined` is returned in that case.

> **Use `runWithOwner` when:** you create new reactive computations (effects, memos) or register cleanups inside async code that was originally initiated from a reactive context. Do not use it merely to *read* signals — signal reads do not need an owner.

---

## `createRoot`

```ts
import { createRoot } from "solid-js"

function createRoot<T>(fn: (dispose: () => void) => T, detachedOwner?: Owner | null): T
```

Creates a new **non-tracked** reactive scope that does **not** automatically dispose when its parent owner is disposed. You receive a `dispose` function and are responsible for calling it.

### Use cases

**1. Top-level reactive code outside any component**

When you create reactive computations at module scope (outside `render()`), there is no parent owner — you get the "never be disposed" warning. `createRoot` gives you an owner and a dispose handle:

```ts
import { createRoot, createSignal, createEffect } from "solid-js"

const { dispose, value } = createRoot((dispose) => {
  const [count, setCount] = createSignal(0)
  createEffect(() => console.log("count:", count()))
  return { dispose, value: count }
})

// Later, tear it all down:
dispose()
```

**2. Rendering detached DOM trees / widgets**

Frameworks and widget managers sometimes need to render Solid trees into elements that aren't yet in the document, or that have an independent lifetime:

```ts
import { createRoot } from "solid-js"
import { render } from "solid-js/web"

let disposeWidget: () => void

function mountWidget(container: HTMLElement) {
  disposeWidget = createRoot((dispose) => {
    render(() => <MyWidget />, container)
    return dispose
  })
}

function unmountWidget() {
  disposeWidget?.()
}
```

**3. Tests**

Wrap reactive code in `createRoot` so signal subscriptions and effects are properly cleaned up between test cases:

```ts
import { createRoot, createSignal, createEffect } from "solid-js"

test("signal updates effect", () => {
  createRoot((dispose) => {
    const [x, setX] = createSignal(0)
    const log: number[] = []
    createEffect(() => log.push(x()))
    setX(1)
    setX(2)
    expect(log).toEqual([0, 1, 2])
    dispose()   // cleans up all effects and subscriptions
  })
})
```

**4. `detachedOwner` — inheriting context without inheriting lifetime**

Pass a captured owner as the second argument to inherit its context (including `useContext` lookups) while keeping independent disposal:

```ts
import { createRoot, getOwner } from "solid-js"

function Component() {
  const owner = getOwner()

  // This root inherits ThemeContext etc. from the component,
  // but won't be disposed when the component unmounts.
  createRoot((dispose) => {
    // useContext(ThemeCtx) works here
  }, owner)
}
```

> **`render()` uses `createRoot` internally.** Every `render(code, element)` call creates a root. The dispose function it returns is `createRoot`'s dispose. You almost never need to call `createRoot` for normal component trees — it's for imperative, outside-JSX reactive graphs.

---

## `createUniqueId`

```ts
import { createUniqueId } from "solid-js"

function createUniqueId(): string
```

Generates an ID that is stable across the server/client boundary, making it safe to use for `id` / `for` / `aria-labelledby` attributes.

```tsx
import { createUniqueId } from "solid-js"

function LabeledInput(props: { label: string }) {
  const id = createUniqueId()

  return (
    <div>
      <label for={id}>{props.label}</label>
      <input id={id} />
    </div>
  )
}
```

Without `createUniqueId`, any ID derived from counters or `Math.random()` will differ between server and client, causing a hydration mismatch. `createUniqueId` guarantees the server and client produce the same sequence of IDs for a given render tree.

---

## `render` — the entry point

```ts
import { render } from "solid-js/web"

function render(
  code: () => JSX.Element,
  element: Element | Document | ShadowRoot | DocumentFragment | Node,
  init?: JSX.Element,
  options?: { owner?: unknown }
): () => void
```

`render` is the application's root owner. It creates a `createRoot` internally and mounts the JSX returned by `code` into `element`. The return value is a **dispose function** — calling it tears down the entire reactive tree and removes rendered content.

```tsx
import { render } from "solid-js/web"
import App from "./App"

const dispose = render(() => <App />, document.getElementById("root")!)

// In tests or hot-reload scenarios:
// dispose()
```

> `code` must be a **function** (a thunk), not a JSX expression directly. `render(<App />, el)` would evaluate `<App />` eagerly, outside the reactive root. `render(() => <App />, el)` defers construction into the root's owner.

Full application wiring — provider stacking, router, query client — is the architecture chapter. Here the key point is: `render` returns a dispose function and that function is `createRoot`'s dispose.

---

## The full interplay

```
render(() => <App />, el)
│
└─ createRoot (new owner)
   │
   └─ App() body runs once (component factory)
      │  signals, memos, effects registered on this owner
      │
      ├─ onMount callbacks queued — fire after DOM insertion
      │
      ├─ DOM inserted into `el`
      │
      ├─ onMount fires (DOM is live)
      │
      └─ (signal change) → createEffect re-runs
            │
            ├─ onCleanup from previous run fires first
            └─ effect body runs, registers new onCleanup
                  │
                  └─ (component removed from tree / dispose())
                        └─ all onCleanup callbacks fire → owner disposed
```

---

## Common patterns

### Interval in a component

```tsx
import { createSignal, onCleanup } from "solid-js"

function Stopwatch() {
  const [elapsed, setElapsed] = createSignal(0)
  const id = setInterval(() => setElapsed(s => s + 1), 1000)
  onCleanup(() => clearInterval(id))

  return <p>{elapsed()}s</p>
}
```

### Event listener that tracks which element to listen to

```tsx
import { createSignal, createEffect, onCleanup } from "solid-js"

function ResizeWatcher(props: { targetId: string }) {
  const [size, setSize] = createSignal({ w: 0, h: 0 })

  createEffect(() => {
    const el = document.getElementById(props.targetId)   // tracked via props getter
    if (!el) return
    const obs = new ResizeObserver(([entry]) => {
      const { width: w, height: h } = entry.contentRect
      setSize({ w, h })
    })
    obs.observe(el)
    onCleanup(() => obs.disconnect())
  })

  return <p>{size().w} × {size().h}</p>
}
```

### Async effect with ownership preserved

```tsx
import { createSignal, createEffect, getOwner, runWithOwner, onCleanup } from "solid-js"

function AsyncSetup() {
  const owner = getOwner()

  createEffect(() => {
    const controller = new AbortController()
    onCleanup(() => controller.abort())

    fetch("/api/subscribe", { signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        runWithOwner(owner, () => {
          // createEffect / onCleanup here belong to AsyncSetup's owner
          createEffect(() => console.log("live data:", data))
        })
      })
  })

  return <div />
}
```

---

## Cheat sheet

| API | When to reach for it |
|---|---|
| `onMount(fn)` | DOM work, focus, third-party init — runs once after first render |
| `onCleanup(fn)` | Dispose any resource; in an effect it re-fires before each re-run |
| `getOwner()` | Capture the current owner before an async boundary |
| `runWithOwner(owner, fn)` | Re-establish an owner after an async boundary so new computations are properly owned |
| `createRoot(fn)` | Manual reactive scope with explicit disposal (top-level code, tests, widgets) |
| `createUniqueId()` | SSR-safe IDs for `id` / `aria-*` / `for` attributes |
| `render(code, el)` | Application entry point; returns a dispose function |

---

## See also

- [01-mental-model.md](01-mental-model.md) — why components run once, how the reactive graph works
- [02-reactivity.md](02-reactivity.md) — `createEffect`, `createMemo`, `untrack`
- [08-context.md](08-context.md) — `createContext`, `useContext`, and how ownership threads context through the tree
