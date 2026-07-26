# Components & props

A Solid component is a **factory function that runs exactly once**. Its job is to create DOM and wire up reactive subscriptions — not to re-render. Everything in this chapter follows from that single fact, and the most important consequence is the one rule you must never break: **props are a live reactive proxy, so you never destructure them.**

> **When you reach for this:** writing any component, passing data down, giving a component default props, forwarding `...rest` to a DOM element, working with `props.children`, or debugging "my prop updates but the child doesn't react." If a prop has stopped updating, the cause is almost always destructuring — jump to [Props are a reactive proxy](#props-are-a-reactive-proxy--never-destructure).

---

## Contents

- [Components are factory functions that run once](#components-are-factory-functions-that-run-once)
- [Props are a reactive proxy — NEVER destructure](#props-are-a-reactive-proxy-never-destructure)
- [The prop helpers](#the-prop-helpers)
- [`mergeProps` — defaults & merging without losing reactivity](#mergeprops-defaults-merging-without-losing-reactivity)
- [`splitProps` — the reactive-safe "destructure"](#splitprops-the-reactive-safe-destructure)
- [The `children` helper](#the-children-helper)
- [Passing callbacks, accessors, and render props](#passing-callbacks-accessors-and-render-props)
- [Typing props with TypeScript (essentials)](#typing-props-with-typescript-essentials)
- [`<Dynamic>` — rendering a component chosen at runtime](#dynamic-rendering-a-component-chosen-at-runtime)
- [Checklist](#checklist)
- [See also](#see-also)


## Components are factory functions that run once

A component is a plain function `(props) => JSX.Element`. Solid calls it **one time** when the component is created, runs the body top to bottom, and returns the JSX (which is already real DOM). It is never called again. There is no re-render, no virtual DOM diff, no reconciliation of the function's output.

```tsx
import { createSignal } from "solid-js"

function Counter() {
  // This whole body runs ONCE.
  const [count, setCount] = createSignal(0)
  console.log("Counter created") // logs exactly one time, ever

  return <button onClick={() => setCount((c) => c + 1)}>{count()}</button>
  //                                                      ▲
  //   {count()} is a reactive binding: only this text node re-runs on update.
}
```

When you click, `setCount` fires, and only the text-node computation that reads `count()` re-runs — updating one DOM node in place. The function `Counter` does not run again.

**Naming & usage.** Components must be **capitalized** (`<Counter />`, not `<counter />`). The compiler treats lowercase tags as native elements and capitalized tags as component calls. A component used in JSX is invoked by the runtime, not by you — `<Counter />` compiles to `createComponent(Counter, props)`, never `Counter(props)`.

> Because the body runs once, anything you want to *react* to a change must live inside a tracked scope — JSX, a `createMemo`, a `createEffect`, or another component's props. A bare read in the body captures a snapshot and freezes it. See [Reactivity](02-reactivity.md) and the [pitfalls chapter](15-pitfalls.md).

---

## Props are a reactive proxy — NEVER destructure

`props` is **not a plain object**. Solid passes every component a proxy whose **getters are the subscription mechanism**. Reading `props.value` *at the moment of use* (inside JSX, a memo, or an effect) subscribes that computation to the parent's `value`, so when the parent changes it, your read re-runs. The subscription happens at the property access, not when the object is handed to you.

Destructuring reads every value **once, eagerly, at call time** — and the component body runs once. You get a plain local variable holding a snapshot. The getter (and therefore the subscription) is gone forever. The value will never update again.

This is the single most common reactivity bug in Solid, and it has three equivalent broken forms:

```tsx
// ❌ Destructuring in the parameter list — reads value once at call time, FROZEN.
function Greeting({ name }: { name: string }) {
  return <h1>Hello {name}</h1> // never updates when parent changes name
}

// ❌ Destructuring in the body — same thing, just one line later.
function Greeting(props: { name: string }) {
  const { name } = props        // snapshot taken here, reactivity lost
  return <h1>Hello {name}</h1>
}

// ❌ Aliasing to a local const — also a one-time read.
function Greeting(props: { name: string }) {
  const name = props.name       // reads the getter ONCE, stores the value
  return <h1>Hello {name}</h1>
}
```

```tsx
// ✅ Access props at the point of use. The read happens inside the JSX
//    binding, so it re-runs whenever the parent updates `name`.
function Greeting(props: { name: string }) {
  return <h1>Hello {props.name}</h1>
}
```

**Why it works:** `props.name` inside JSX compiles to a function the runtime calls in a tracking scope. Each call hits the proxy getter, which registers the dependency and returns the current value. Move the read out of a tracking scope (or out of the proxy via destructuring) and there is nothing to re-run.

The same rule applies to **store fields** (`store.user.name` stays reactive; `const { user } = store` does not) — see [Stores](06-stores.md).

> **The mental shorthand:** in Solid you pass *the ability to read a value later*, not the value. `props.x` is that ability. Destructuring spends it immediately.

**What about non-reactive props?** Even if a prop never changes, prefer `props.x` — it costs nothing, it's consistent, and it future-proofs the component against the prop becoming reactive later. The lint rule `solid/reactivity` (eslint-plugin-solid) flags destructuring for exactly this reason.

### When you genuinely need to "destructure"

You can't use JS destructuring, but Solid gives you two reactivity-preserving helpers that cover the real use cases: `mergeProps` (add defaults / merge) and `splitProps` (separate some keys from the rest). Use these instead of spread/destructure.

---

## The prop helpers

| Helper | Signature | Purpose |
| --- | --- | --- |
| `mergeProps` | `mergeProps(...sources): MergedProps` | Merge multiple prop-like objects into one reactive proxy. Right-most wins. Use for **default props** and combining prop sources without losing reactivity. |
| `splitProps` | `splitProps(props, ...keyGroups): [...groups, rest]` | The reactive-safe "destructure": split a props proxy into one proxy per key-group plus a final `rest` proxy. Both sides stay reactive. Use to **forward `...rest`** to a DOM element. |
| `children` | `children(() => props.children): Accessor & { toArray }` | Resolve `props.children` once, memoize the result, and give you an accessor you can call to read/inspect/transform the resolved children. |

All three come from the main package:

```ts
import { mergeProps, splitProps, children } from "solid-js"
```

---

## `mergeProps` — defaults & merging without losing reactivity

`mergeProps(...sources)` returns a **new reactive proxy** that reads through to its sources on every access. Later sources override earlier ones, key by key. Because reads are lazy (the merged proxy has getters too), reactivity is preserved end to end.

The canonical use is **default props**. Do not use `||` or destructuring defaults — both read once and break reactivity (and `||` also clobbers legitimate falsy values like `0` or `""`).

```tsx
import { mergeProps } from "solid-js"

type GreetingProps = { name?: string; greeting?: string }

// ❌ `||` reads once AND breaks on falsy values; the default never re-evaluates.
function BadGreeting(props: GreetingProps) {
  const greeting = props.greeting || "Hi" // frozen + wrong for greeting=""
  return <h1>{greeting}, {props.name}</h1>
}

// ✅ mergeProps layers defaults UNDER the incoming props, reactively.
function Greeting(props: GreetingProps) {
  const merged = mergeProps({ name: "stranger", greeting: "Hi" }, props)
  return <h1>{merged.greeting}, {merged.name}</h1>
  //          ▲ reads through to props.greeting if present, else the default —
  //            and re-runs if either changes.
}
```

Key points:

- **Order matters.** `mergeProps(defaults, props)` — defaults first so real props win. Reverse the order and your defaults would override the caller.
- **`undefined` falls through to the next source**, so a default fills in only when the incoming prop is missing/`undefined` (unlike `||`, an explicit `0`/`""`/`false` is kept).
- **A source can be a function** (an accessor); `mergeProps` reads it lazily, so you can merge in dynamically computed props.
- It replaces React's `defaultProps` entirely — there is no static `Component.defaultProps` in Solid.

```tsx
// Merging dynamic + static + incoming props, all kept reactive:
const merged = mergeProps(
  { variant: "primary" },          // static defaults
  () => ({ disabled: isBusy() }),  // a function source, re-read on access
  props                            // caller props win last
)
```

---

## `splitProps` — the reactive-safe "destructure"

`splitProps(props, group1, group2, ..., )` takes the props proxy and a list of key arrays. It returns an array of proxies: **one proxy per key group**, then a final proxy holding **everything not named** (the `rest`). Every returned proxy is reactive — reads still go through the original getters.

This is how you forward unknown attributes to a DOM element while pulling out the few you handle yourself. Spreading the original `props` *and* reading individual keys would consume the same getters twice and is exactly what `splitProps` exists to avoid.

```tsx
// ❌ Plain destructure to forward rest — both `class` and `rest` are frozen,
//    and `...rest` here is an ordinary object snapshot, not reactive.
function Input(props: JSX.InputHTMLAttributes<HTMLInputElement>) {
  const { class: cls, ...rest } = props
  return <input class={cls} {...rest} />
}
```

```tsx
// ✅ splitProps keeps both `local` and `rest` reactive.
//    (This is a real ui/input.tsx pattern.)
import { splitProps, type JSX } from "solid-js"
import { cn } from "@/utils"

function Input(props: JSX.InputHTMLAttributes<HTMLInputElement>) {
  const [local, rest] = splitProps(props, ["class", "type"])
  return (
    <input
      type={local.type}
      class={cn("rounded-md border px-3 py-1", local.class)}
      {...rest}   // spreading a splitProps proxy stays reactive
    />
  )
}
```

**Multi-bucket form.** Pass several key arrays to split into several proxies. Useful when, e.g., one set of props goes to a wrapper and another to an inner control:

```tsx
const [layout, control, rest] = splitProps(
  props,
  ["class", "style"],        // → layout: { class, style }
  ["value", "onInput"]       // → control: { value, onInput }
)                            // → rest: everything else
// layout.class, control.value, and ...rest are all reactive.
```

> **Why spreading a `splitProps`/`mergeProps` proxy is safe** but spreading a destructured object isn't: the JSX spread `{...rest}` is compiled to read each key reactively when `rest` is a Solid proxy. A plain object spread is evaluated once. Always spread the proxy Solid gave you, never a hand-built object of snapshots.

---

## The `children` helper

`props.children` is **lazy and may re-create child components on every access**. Reading it repeatedly (e.g. once to count, once to render) can run the children's creation logic multiple times. `children(() => props.children)` solves this:

```ts
import { children } from "solid-js"
const resolved = children(() => props.children)
```

It returns a **memoized accessor** (`Accessor<ResolvedChildren>`) with one extra method, `.toArray()`. What it does:

- **Resolves** the children once — calls any child component functions, flattens nested arrays, and turns the result into concrete elements/values.
- **Memoizes** — subsequent reads return the same resolved result; children aren't re-created on every access.
- **Stays reactive** — if `props.children` itself changes (dynamic children), the accessor updates.

Call it (`resolved()`) to read the resolved children, or `resolved.toArray()` to always get a flat array (handy for iterating, counting, or wrapping each child):

```tsx
import { children, type JSX, type ParentProps } from "solid-js"

// Wrap each child in a list item, regardless of how many were passed.
function List(props: ParentProps) {
  const resolved = children(() => props.children)
  return (
    <ul>
      {resolved.toArray().map((child) => (
        <li>{child}</li>
      ))}
    </ul>
  )
}
```

You can also **inspect or transform** resolved children — e.g. apply a class to each, or read a count:

```tsx
import { children, createMemo, type ParentProps } from "solid-js"

function Toolbar(props: ParentProps) {
  const resolved = children(() => props.children)
  const count = createMemo(() => resolved.toArray().length)
  return (
    <div role="toolbar" aria-label={`${count()} actions`}>
      {resolved()}
    </div>
  )
}
```

> **When you don't need it:** if you just render `{props.children}` once and never touch it otherwise, you don't need the helper — passing children straight through is fine and common. Reach for `children()` when you read children more than once, or need to inspect/transform them.

---

## Passing callbacks, accessors, and render props

**Callbacks** are just function props — pass them straight through:

```tsx
function Child(props: { onSave: (v: string) => void }) {
  return <button onClick={() => props.onSave("hi")}>Save</button>
}
```

**Passing a reactive value down.** Remember the proxy rule applies to *what you pass*, not just how you read. Passing `value={count()}` hands the child a **snapshot** taken now; passing `value={count}` (the accessor) or letting the child read `props.value` keeps it live.

```tsx
// Parent
const [count, setCount] = createSignal(0)

<Display value={count()} />   // snapshot: Display sees 0 forever IF it stores it,
                              // but it's STILL reactive if Display reads props.value in JSX,
                              // because the parent JSX re-runs the {count()} read.
```

The subtlety: `value={count()}` *looks* like a snapshot, but the parent's JSX expression `count()` is itself a tracked binding, so Solid re-passes the new value to the child on change, and the child's `props.value` read picks it up. The snapshot bug appears when you read `props.value` **outside** a tracking scope in the child (e.g. destructure it). Pass an accessor (`value={count}`) only when the child needs to control *when* it reads, or to defer the read. See the [pitfalls chapter](15-pitfalls.md#6-snapshotting-a-signal-when-passing-it-down) for the failure modes.

**Render props (children-as-function).** A child whose `children` is a function lets the child supply arguments back up — the standard pattern for "give me your data, I'll render it." Type it with `FlowComponent`:

```tsx
import { type FlowComponent } from "solid-js"

// children is a function receiving the resolved user.
const WithUser: FlowComponent<{ id: string }, (user: User) => JSX.Element> = (props) => {
  const user = loadUser(props.id) // some accessor
  return <>{props.children(user())}</>
}

// Usage — the function child receives `user`:
<WithUser id="42">{(user) => <span>{user.name}</span>}</WithUser>
```

Solid's built-in `<For>` and `<Show>` (with a function child) use exactly this pattern — see [Control flow](04-control-flow.md).

---

## Typing props with TypeScript (essentials)

Solid ships a small family of component types. Pick by whether the component takes `children`:

| Type | Meaning |
| --- | --- |
| `Component<P>` | Base: `(props: P) => JSX.Element`. **No implicit `children`** — add it to `P` yourself if needed. |
| `ParentComponent<P>` | `P` plus an **optional** `children?: JSX.Element`. For components that accept arbitrary children. |
| `VoidComponent<P>` | `P` with `children?: never` — **forbids** children (errors if someone passes them). |
| `FlowComponent<P, C>` | `P` with a **required** `children: C`. `C` defaults to `JSX.Element`; set it to a function type for render props. |
| `ParentProps<P>` / `VoidProps<P>` / `FlowProps<P, C>` | The prop *shape* helpers behind the component types — use when you type `props` directly instead of the component. |
| `ComponentProps<T>` | Extracts the props of a component **or native element** — `ComponentProps<'button'>` gives `JSX.ButtonHTMLAttributes<HTMLButtonElement>`; `ComponentProps<typeof MyComp>` gives that component's props. |

```tsx
import {
  type Component,
  type ParentComponent,
  type VoidComponent,
  type ComponentProps,
} from "solid-js"

// Self-contained, no children:
const Badge: Component<{ label: string }> = (props) => <span>{props.label}</span>

// Accepts children:
const Card: ParentComponent<{ title: string }> = (props) => (
  <section><h2>{props.title}</h2>{props.children}</section>
)

// Wrapping a native <button>: extend its props so all native attrs pass through.
const Button: VoidComponent<ComponentProps<"button"> & { loading?: boolean }> = (props) => {
  const [local, rest] = splitProps(props, ["loading", "children"])
  // ...but VoidComponent forbids children — for a button you'd use Component instead.
}
```

A common, robust pattern for "styled native element" components: take `ComponentProps<'button'>` (or the relevant tag), `splitProps` out the keys you handle, and spread `...rest` onto the element so every native attribute (`id`, `aria-*`, `data-*`, event handlers) flows through automatically.

> Full TypeScript depth — generic `<For>`, typing refs, signals/stores, `JSX.Element` vs `Component` — is its own chapter: [TypeScript](14-typescript.md). The above is the working subset for props.

---

## `<Dynamic>` — rendering a component chosen at runtime

When the component (or tag) to render is decided at runtime, don't branch with a chain of `<Show>`s — use `<Dynamic component={...}>`. It renders the given component or native tag and forwards all other props to it.

```tsx
import { Dynamic } from "solid-js/web" // note: from solid-js/web, not solid-js

function Field(props: { multiline: boolean; value: string }) {
  return (
    <Dynamic
      component={props.multiline ? "textarea" : "input"}
      value={props.value}
    />
  )
}
```

`component` may be a native tag string (`"div"`), a component reference, or `undefined` (renders nothing). It's the idiomatic way to pick a heading level, swap an icon set, or render a registry of components by key. Full treatment in [Control flow](04-control-flow.md).

---

## Checklist

- ✅ Components are `PascalCase`, run **once**, return `JSX.Element`.
- ✅ Read props at point of use: `props.x`. **Never** `{ x }` in params, `const { x } = props`, or `const x = props.x`.
- ✅ Defaults → `mergeProps(defaults, props)`, never `||` or destructure defaults.
- ✅ "Destructure" for forwarding → `splitProps(props, [...keys])`, then spread the `rest` proxy.
- ✅ Reading children more than once / inspecting them → `children(() => props.children)`, use `.toArray()`.
- ✅ Type with `Component` / `ParentComponent` / `VoidComponent` / `FlowComponent`; extend native elements with `ComponentProps<'tag'>`.

## See also

- [Reactivity](02-reactivity.md) — signals, memos, effects, and why reads must live in tracking scopes
- [Control flow](04-control-flow.md) — `<Show>`/`<For>`/`<Dynamic>` and the render-prop pattern
- [Stores](06-stores.md) — the same "don't destructure" rule for deep reactive state
- [Pitfalls & anti-patterns](15-pitfalls.md) — the destructured-props bug and its cousins, with fixes
- [TypeScript](14-typescript.md) — full prop/component typing
