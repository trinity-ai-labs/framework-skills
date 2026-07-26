# Mental Model

How Solid actually works under the hood — fine-grained reactivity with no virtual DOM, components that run once as factories, and a reactive graph that updates individual DOM nodes directly. Internalise this chapter and every other API in the skill becomes obvious; skip it and you will fight the framework.

---

## The one big idea: no re-render, no diffing

React and Solid look almost identical on the page — JSX, components, hooks-shaped primitives — but they are built on opposite foundations.

In React, your component **function is the unit of update**. State changes, React calls your function again, you produce a new virtual DOM tree, React diffs it against the previous tree, and patches the real DOM. Everything — `useMemo`, `useCallback`, dependency arrays, `React.memo` — exists to make that repeated re-execution cheaper.

In Solid there is **no virtual DOM and nothing re-renders**. JSX compiles to code that creates real DOM nodes once, then wires up tiny reactive subscriptions around just the parts that can change. When a value changes, Solid does not call your component again and does not diff anything — it re-runs only the specific reactive computations that read that value, and those computations write directly to the exact text node, attribute, or DOM range they own.

```tsx
import { createSignal } from "solid-js"

function Counter() {
  const [count, setCount] = createSignal(0)
  return <button onClick={() => setCount(c => c + 1)}>Count: {count()}</button>
}
```

When you click, Solid does **not** re-run `Counter`. It re-runs only the one binding that produces the text `Count: …` and sets the text node's value. No new VNodes, no diff, no reconciliation. The `<button>` element, the click handler, and the surrounding structure are created once and never touched again.

> **Why this matters.** In Solid, "performance" is not about *avoiding* re-renders (there are none to avoid) — it is about keeping each reactive computation narrow so it touches as little DOM as possible. There is no `useMemo` for "stabilising a re-render"; memos exist to cache *derived computation*, not to cut down re-execution of components.

---

## The component is a factory that runs exactly ONCE

The single most important consequence of the model: **a component function runs once, when it's created, and never again.** It is a *factory* — its job is to set up the DOM and the reactive wiring, then get out of the way.

```tsx
import { createSignal } from "solid-js"

function Greeting() {
  console.log("Greeting body ran")     // ← logs exactly ONCE, ever
  const [name, setName] = createSignal("world")

  // This `if` runs once. It does NOT re-evaluate when name() changes.
  if (name() === "world") {
    console.log("name was 'world' at construction time")
  }

  return <h1>Hello {name()}</h1>        // the {name()} binding stays live
}
```

What "runs once" implies, concretely:

- **Local variables are computed once.** `const upper = name().toUpperCase()` is evaluated a single time at construction and then frozen — it will never reflect later changes to `name()`. To stay live it must be a function: `const upper = () => name().toUpperCase()`.
- **Plain control flow in the body doesn't react.** An `if`, a `for`, a `switch`, a ternary, or `.map()` in the component body runs once. That is exactly why Solid ships `<Show>`, `<For>`, `<Switch>`, `<Index>` and `<Dynamic>` — components whose *internals* are reactive even though the surrounding factory is not. (→ [`04-control-flow.md`](04-control-flow.md))
- **There is no "render method" to keep pure.** You can do imperative setup, create resources, subscribe to things, and start timers in the body — it happens once, like a constructor. (Cleanup goes through `onCleanup`; → [`05-lifecycle-and-ownership.md`](05-lifecycle-and-ownership.md))
- **Props are not snapshots.** Because the function never re-runs, `props` is not a per-render copy — it is a live, getter-backed object. `props.value` re-reads the current value every time you access it. This is why **you never destructure props** (destructuring reads each field once, at construction, and freezes it). (→ [`03-components-and-props.md`](03-components-and-props.md))

```tsx
// ❌ frozen at construction — `label` never updates
function Badge(props: { count: number }) {
  const label = `${props.count} items`   // evaluated once
  return <span>{label}</span>
}

// ✅ live — the binding re-reads props.count whenever it changes
function Badge(props: { count: number }) {
  return <span>{props.count} items</span>
}
```

---

## Tracking scopes and reactive computations

A **reactive computation** (also called a *tracking scope*) is a function that Solid runs *while watching which signals it reads*. Solid records every signal accessed during that run as a **dependency**. When any dependency changes, Solid re-runs the computation.

There are exactly three kinds of tracking scope, and you create them with these primitives (→ [`02-reactivity.md`](02-reactivity.md)):

| Tracking scope | Created by | Re-runs to… |
| --- | --- | --- |
| **Render binding** | the compiler, around each `{...}` in JSX | update a DOM text node / attribute |
| **Memo** | `createMemo(fn)` | recompute a cached derived value |
| **Effect** | `createEffect(fn)` (also `createRenderEffect`, `createComputed`) | run a side effect |

Reads that happen **outside** any tracking scope are *not* tracked — they read the current value once and create no subscription. The bare component body is one such non-tracking place; so is a plain event handler, a `setTimeout` callback, or anything inside `untrack(...)`.

```tsx
import { createSignal, createEffect } from "solid-js"

const [count, setCount] = createSignal(0)

// Inside a tracking scope → subscribes, re-runs on every change:
createEffect(() => console.log("tracked:", count()))

// In a plain handler → NOT a tracking scope → reads once, no subscription:
const onClick = () => console.log("read once:", count())
```

> **The mental test:** "Is this read happening inside a function that Solid is currently watching?" If yes, it subscribes and stays live. If no (component body, event handler, `untrack`), it's a one-shot read.

---

## Reactivity tracks function CALLS, not values

This is the rule that trips up everyone coming from React, and it is the key to the whole system.

A signal is a **getter/setter pair**, not a value:

```tsx
import { createSignal } from "solid-js"

const [count, setCount] = createSignal(0)
//      ▲ getter        ▲ setter
```

`count` is a function. **The act of calling it — `count()` — is the subscription.** When a tracking scope calls `count()`, Solid links that scope to the signal. Nothing else subscribes: not assigning the getter to a variable, not passing it around, not logging the function itself. Only the *call*.

This is why the distinction between passing `count` and passing `count()` is load-bearing:

```tsx
// Pass the GETTER → the receiver can call it inside its own tracking scope → stays live
<Display value={count} />            // value: () => number     ✅ reactive downstream

// Pass the VALUE → you call it HERE, freezing the result at this moment → dead
<Display value={count()} />          // value: number           ❌ snapshot
```

```tsx
// ❌ A common anti-pattern: reading in the body and passing the value
function Parent() {
  const [user] = createSignal({ name: "Ada" })
  const name = user().name              // read once, frozen
  return <Child name={name} />          // Child can never see updates
}

// ✅ Pass an accessor (a function); let the child read it in its own tracked scope
function Parent() {
  const [user] = createSignal({ name: "Ada" })
  return <Child name={() => user().name} />   // stays live
}
```

The same rule explains why destructuring props breaks reactivity (`const { name } = props` *calls* the getter once) and why JSX `{count()}` is reactive (the compiler wraps it in a tracking scope, so the call happens *inside* something Solid watches). It's always the same rule: **the call inside a tracking scope is the subscription.**

---

## The reactive graph

Under the hood, Solid maintains a directed graph of **sources** and **observers**.

- A **source** is anything that can be read and can notify: a signal, a memo, or a store property. It holds a list of observers.
- An **observer** is any tracking scope (memo or effect/render binding). It holds a list of the sources it read on its last run.

The links are bidirectional and rebuilt every run: each time a computation executes, Solid clears its old source list and records exactly the sources it touched *this* time. So if a branch isn't taken, its signals aren't dependencies — dependency sets are dynamic, never a static array you declare.

```
sources                 observers
                ┌────────────────────────────────────┐
[signal a] ─────┤                                     │
                ├──▶ [memo: a + b] ──▶ [effect: log]  │
[signal b] ─────┤                  └──▶ [render: text]│
                └────────────────────────────────────┘
```

**Push + pull, glitch-free.** When you write a signal, Solid does a two-phase update:

1. **Push (mark):** it walks the observer graph and marks everything downstream as *stale* — but does not recompute yet.
2. **Pull (compute):** it then evaluates in dependency order, so a node is only recomputed *after* all of its own stale sources are up to date.

This ordering is what makes Solid **glitch-free**: a computation that depends on two things derived from the same signal will never observe an inconsistent in-between state, and never runs twice for one logical change.

```tsx
import { createSignal, createMemo, createEffect } from "solid-js"

const [a, setA] = createSignal(1)
const sumIsEven = createMemo(() => (a() + a()) % 2 === 0)
createEffect(() => console.log("a:", a(), "even sum:", sumIsEven()))

setA(2)   // effect runs ONCE with consistent values — never with a half-updated sumIsEven
```

**Synchronous & topological.** Updates run synchronously by default; `setA(2)` has flushed its effects by the time the call returns (memos and render bindings update eagerly; effects are queued to the end of the current microtask-free batch but still run before control returns to the event loop). When you make several writes that should be treated as one change, wrap them in `batch(...)` so observers run once at the end. (→ [`02-reactivity.md`](02-reactivity.md))

---

## JSX compiles to real DOM + reactive bindings

Solid's JSX is **not** `React.createElement`. The Solid compiler (`babel-preset-solid`, used through `vite-plugin-solid` in a Vite app) transforms JSX into:

1. a **template** — a static HTML string cloned once into real DOM nodes, and
2. **reactive bindings** — small wrapper functions around only the dynamic parts.

A rough sketch of what the compiler emits:

```tsx
// You write:
function Hello(props: { name: string }) {
  return <h1 class="title">Hello {props.name}!</h1>
}

// The compiler emits something like (simplified):
import { template, insert, effect, setAttribute } from "solid-js/web"

const _tmpl = template(`<h1 class=title>Hello !`)   // parsed & cloned, once

function Hello(props) {
  const el = _tmpl()                                 // real <h1>, cloned from template
  insert(el, () => props.name, /* marker */)         // ← reactive binding for {props.name}
  return el
}
```

The static structure (`<h1 class="title">`, the literal text `Hello ` and `!`) lives in the template and is created exactly once. Only `{props.name}` becomes a tracked binding via `insert`. A dynamic attribute would similarly compile to a tracked `setAttribute`/`className`/`style` call. This is why Solid's per-update work is proportional to *what changed*, not to the size of the component tree.

> **You rarely think about the compiler — but two things leak through.** (1) JSX uses Solid attribute names: `class` not `className`, plus `classList`, `style` objects, `onClick`, and `ref`. (2) Because dynamic expressions become tracking scopes, putting a signal read *directly* in JSX (`{count()}`) is reactive, while pre-reading it into a const in the body (`const c = count()`) is not.

---

## The three things that re-run — and the one that doesn't

Commit this to memory:

**Re-runs on dependency change:**
1. **Render bindings** — the compiled `{...}` expressions in JSX (text, attributes, `class`/`style`, props passed as accessors).
2. **Memos** — `createMemo(fn)`; recompute when a source changes, and notify downstream only when the *result* changes.
3. **Effects** — `createEffect(fn)` (and the rarer `createRenderEffect`, `createComputed`); re-run for side effects.

**Does NOT re-run:**
4. **The component function body.** Ever. It's the factory.

If you find yourself wanting code to "run again when X changes," the answer is never "re-run the component" — it's "put that code in one of the three tracking scopes above" (usually a memo if you're deriving a value, an effect if you're causing a side effect).

---

## For engineers coming from React

| Concept | React | Solid |
| --- | --- | --- |
| Update unit | Re-run the component, diff a VDOM tree | Re-run only the computations that read the changed value; no VDOM, no diff |
| Component body | Runs on **every** render | Runs **once** (a factory) |
| State read | `const v = useState(...)` → `v` is a value | `const [v] = createSignal(...)` → `v` is a **getter**; `v()` reads *and subscribes* |
| Subscription | Implicit via re-render + deps arrays | The **getter call** inside a tracking scope |
| `useMemo` | Caches across re-renders; needs a deps array | `createMemo` caches a derived value; **dependencies are auto-tracked** — no deps array |
| `useCallback` | Stabilises function identity across renders | **Not needed** — the body runs once, so functions are already stable |
| Dependency arrays | You list deps manually; stale-closure bugs | None — deps are tracked by what you *call* at runtime |
| Props | A fresh **snapshot** each render | A **live** getter-backed object; `props.x` re-reads current value |
| Destructuring props | Fine (it's a snapshot anyway) | **Breaks reactivity** — reads each field once, freezing it |
| `useEffect` | Runs after commit; cleanup + deps array | `createEffect` runs after render; cleanup via `onCleanup`; **no deps array** |
| `useRef` | Mutable box that survives renders | A plain `let`/`const` in the body survives, because the body never re-runs |
| Conditional rendering | `cond && <X/>` / ternary re-evaluated each render | `<Show>` / `<Switch>` — JS conditionals in the body run once |
| Lists | `arr.map()` re-runs and diffs each render | `<For>` (keyed by item identity) / `<Index>` (keyed by position) |
| Context | `useContext`, re-renders consumers | `useContext` returns reactive values; only the bindings that read them update |

The mantra: **React re-runs and diffs; Solid subscribes and updates in place.** Most React optimisation reflexes (memoising callbacks, splitting components to dodge re-renders, watching deps arrays) are simply *not concepts* in Solid.

---

## Common confusion — read this list twice

- **"I read the signal in the component body and it never updates."** The body runs once. Reads there are frozen. Move the read into JSX, a memo, or an effect — anywhere that's a tracking scope.
- **"I destructured props / a store and lost reactivity."** Destructuring *calls* the getter once. Keep `props.x` access live, or use `splitProps`/`mergeProps`. (→ [`03-components-and-props.md`](03-components-and-props.md))
- **"I passed `count()` to a child and it's stale."** You passed the value, not the getter. Pass `count` (or `() => count()`/`() => derive(count())`) so the child reads inside its own tracking scope.
- **"I forgot the parentheses: `{count}` shows `() => …`."** A signal is a function; you must *call* it to read. JSX renders the function itself if you forget the `()`.
- **"My effect runs but the value is stale."** You read the signal outside the tracked function (e.g. captured it into a `const` first, or read it inside a nested non-tracking callback). Only direct calls inside the effect's function subscribe.
- **"I expected the component to re-run when state changed."** It won't, by design. Nothing re-renders. Only the three tracking scopes (render bindings, memos, effects) re-run.
- **"Where's my deps array?"** There isn't one. Solid tracks whatever you *call* during the run. Conditionally-read signals are conditionally tracked — the dependency set is dynamic and exact.
- **"I added `useMemo`/`useCallback` out of habit."** Not needed. Functions defined in the once-running body are already stable; `createMemo` is for caching *expensive derivations*, not for fixing re-renders (there are none).
- **"An `if` in my JSX/body doesn't switch when the condition changes."** Plain conditionals run once. Use `<Show>`/`<Switch>` so the *internal* tracking updates.

---

## See also

- [`02-reactivity.md`](02-reactivity.md) — the primitives: `createSignal`, `createMemo`, `createEffect`, `on`, `untrack`, `batch`
- [`03-components-and-props.md`](03-components-and-props.md) — why props are live and must not be destructured
- [`04-control-flow.md`](04-control-flow.md) — `<Show>`/`<For>`/`<Index>`/`<Switch>`, the reactive replacements for `if`/`map`
- [`15-pitfalls.md`](15-pitfalls.md) — the anti-patterns this chapter warns about, in depth
- Official docs: <https://docs.solidjs.com>
