# TypeScript

> **When you reach for this:** when TypeScript rejects a prop, a ref, a directive, or an event handler that looks right; when you're wiring up a context and fighting `T | undefined`; when you need to forward native element props without reimplementing them.

Solid ships full TypeScript support out of the box. The types live in `solid-js` and `solid-js/web`. This chapter covers every place the types are non-obvious or where Solid's idioms diverge from what React developers expect.

---

## Contents

- [Key types at a glance](#key-types-at-a-glance)
- [Signals](#signals)
- [Component types](#component-types)
- [Props typing](#props-typing)
- [Generic components](#generic-components)
- [Polymorphic components (the `as` prop)](#polymorphic-components-the-as-prop)
- [`splitProps` and `mergeProps`](#splitprops-and-mergeprops)
- [Refs](#refs)
- [Stores](#stores)
- [Resources](#resources)
- [Context](#context)
- [Directives (`use:`)](#directives-use)
- [Event handling](#event-handling)
- [`JSX.Element` vs `ValidComponent`](#jsxelement-vs-validcomponent)
- [A worked example: a typed, forwarding button](#a-worked-example-a-typed-forwarding-button)
- [See also](#see-also)


## Key types at a glance

| Type | Where it lives | What it is |
|---|---|---|
| `Accessor<T>` | `solid-js` | `() => T` — a signal getter |
| `Setter<T>` | `solid-js` | The setter returned by `createSignal` |
| `Signal<T>` | `solid-js` | `[Accessor<T>, Setter<T>]` |
| `Component<P>` | `solid-js` | `(props: P) => JSX.Element` |
| `ParentComponent<P>` | `solid-js` | Component that accepts `children?: JSX.Element` |
| `VoidComponent<P>` | `solid-js` | Component that must NOT have children |
| `FlowComponent<P, C>` | `solid-js` | Component where children are required and typed as `C` |
| `ParentProps<P>` | `solid-js` | `P & { children?: JSX.Element }` |
| `VoidProps<P>` | `solid-js` | `P & { children?: never }` |
| `FlowProps<P, C>` | `solid-js` | `P & { children: C }` |
| `Resource<T>` | `solid-js` | Reactive async resource returned by `createResource` |
| `Store<T>` | `solid-js/store` | Readonly deep proxy of `T` |
| `SetStoreFunction<T>` | `solid-js/store` | Setter for a store |
| `Ref<T>` | `solid-js` | `T \| ((el: T) => void)` — ref prop type |
| `ValidComponent` | `solid-js` | `keyof JSX.IntrinsicElements \| Component<any> \| (string & {})` — anything usable as a tag/component |
| `ComponentProps<T>` | `solid-js` | The props of `T`, where `T` is a tag name (`"div"`) or a component |
| `JSX.Element` | `solid-js` | Any valid Solid child |
| `JSX.CSSProperties` | `solid-js` | Style object type |
| `JSX.EventHandler<T, E>` | `solid-js` | Typed event handler |

---

## Signals

### Basic typing

```ts
import { createSignal } from "solid-js"
import type { Accessor, Setter, Signal } from "solid-js"

// Inferred: createSignal(0) → Signal<number>
const [count, setCount] = createSignal(0)
//     ^──── Accessor<number>   ^──── Setter<number>

// Explicit type parameter
const [name, setName] = createSignal<string>("")

// Without initial value: T becomes T | undefined
const [user, setUser] = createSignal<User>()
//     ^──── Accessor<User | undefined>
```

### Destructured types

```ts
import type { Accessor, Setter } from "solid-js"

// Pass an accessor around without carrying the setter
function Display(props: { value: Accessor<number> }) {
  return <span>{props.value()}</span>
}

// Accept a setter as a prop
function Input(props: { onValue: Setter<string> }) {
  return <input onInput={e => props.onValue(e.currentTarget.value)} />
}
```

### `Setter<T>` accepts a value or an updater

```ts
const [n, setN] = createSignal(0)

setN(1)              // set directly
setN(prev => prev + 1) // update function

// The updater overload makes Setter<T> typed as:
// (value: T | ((prev: T) => T)) => T
```

---

## Component types

### `Component<P>` — the base

```ts
import type { Component } from "solid-js"

// Component<P> = (props: P) => JSX.Element
type MyProps = { label: string }
const Button: Component<MyProps> = (props) => (
  <button>{props.label}</button>
)
```

### `ParentComponent<P>` — accepts children

```ts
import type { ParentComponent } from "solid-js"

const Card: ParentComponent<{ title: string }> = (props) => (
  <div class="card">
    <h2>{props.title}</h2>
    {props.children}
  </div>
)
// props.children is JSX.Element | undefined — optional
```

### `VoidComponent<P>` — must NOT have children

```ts
import type { VoidComponent } from "solid-js"

// If someone passes children to this, TypeScript will error.
const Avatar: VoidComponent<{ src: string }> = (props) => (
  <img src={props.src} />
)
```

### `FlowComponent<P, C>` — required, typed children

```ts
import type { FlowComponent } from "solid-js"
import type { JSX } from "solid-js"

// FlowComponent<P, C> requires children: C
// Used for components like <Show>, <For> where children are a render function.
const Wrapper: FlowComponent<{ class?: string }, JSX.Element> = (props) => (
  <div class={props.class}>{props.children}</div>
)
```

### When to use a plain function signature instead

For internal or simple components, a plain typed function is idiomatic and avoids the ceremony:

```ts
// Fine for internal components — no need to import a component type
function Label(props: { text: string; bold?: boolean }): JSX.Element {
  return <span style={{ "font-weight": props.bold ? "bold" : "normal" }}>{props.text}</span>
}
```

Use `Component<P>` / `ParentComponent<P>` when you're exporting a component as a value (e.g., passing it as a prop, storing it in an array, or publishing it in a library).

---

## Props typing

### Inheriting native element props

```ts
import type { ComponentProps } from "solid-js"
import { splitProps } from "solid-js"

// Grab the full native props type for a <button>
type ButtonProps = ComponentProps<"button"> & {
  loading?: boolean
}

function LoadingButton(props: ButtonProps) {
  const [local, rest] = splitProps(props, ["loading", "children"])
  return (
    <button {...rest} disabled={props.loading || rest.disabled}>
      {local.loading ? "…" : local.children}
    </button>
  )
}
```

`ComponentProps<"button">` is equivalent to `JSX.ButtonHTMLAttributes<HTMLButtonElement>` but shorter. Use it for any HTML element tag string.

### Extending `JSX.IntrinsicElements`

You can also reference native attribute types directly:

```ts
import type { JSX } from "solid-js"

// JSX.IntrinsicElements["div"] is the type of all valid <div> props
type DivProps = JSX.IntrinsicElements["div"]

// Style objects
function Styled(props: { style?: JSX.CSSProperties }) {
  return <div style={props.style}>content</div>
}

// Usage
<Styled style={{ "background-color": "red", "font-size": "14px" }} />
// Note: Solid style objects use kebab-case strings as keys, not camelCase
```

> **`JSX.CSSProperties` uses kebab-case keys**, not camelCase. `backgroundColor` is not a valid key. Use `"background-color"` instead.

### Children typing

```ts
import type { JSX } from "solid-js"

type Props = {
  children: JSX.Element          // exactly one valid child expression
  label: string
}

// For multiple children or optional children, use ParentProps instead.
import type { ParentProps } from "solid-js"
type CardProps = ParentProps<{ title: string }>
```

---

## Generic components

A component is just a function, so it can take type parameters like any other. Solid has **no `forwardRef` and no `memo` wrapper** to fight with, so generics work exactly as they do in plain TypeScript — this is one place Solid is markedly simpler than React.

```tsx
import { For } from "solid-js"
import type { Accessor, JSX } from "solid-js"

type ListProps<T> = {
  items: T[]
  fallback?: JSX.Element
  children: (item: T, index: Accessor<number>) => JSX.Element
}

// Note the trailing comma in <T,> — see the gotcha below.
function List<T,>(props: ListProps<T>) {
  return (
    <ul>
      <For each={props.items} fallback={props.fallback}>
        {(item, index) => <li>{props.children(item, index)}</li>}
      </For>
    </ul>
  )
}

// T is inferred from `items`; the render prop is fully typed.
type User = { id: number; name: string }
const users: User[] = [{ id: 1, name: "Ada" }]

<List items={users} fallback={<li>No users</li>}>
  {(user, i) => <span>{i() + 1}. {user.name}</span>}
</List>
```

> **The `.tsx` trailing-comma gotcha.** In a `.tsx` file, `<T>` at the start of a type-parameter list is ambiguous with a JSX tag. Write `function List<T,>(…)` or `const List = <T,>(props: ListProps<T>) => …`. A bare `const List = <T>(props) => …` is parsed as JSX and fails to compile. Declaring with the `function` keyword usually avoids this, but the trailing comma is the reliable fix in both forms.

Type the render prop's `index` as `Accessor<number>` to match `<For>` (call it: `i()`), or as plain `number` to match `<Index>`. → [Control flow](04-control-flow.md)

**Don't annotate a generic component with `Component<P>`.** `const List: Component<ListProps<T>>` has nowhere to bind `T` — the type alias is not generic over the component. Use a plain function signature instead (see [When to use a plain function signature](#when-to-use-a-plain-function-signature-instead)).

---

## Polymorphic components (the `as` prop)

A polymorphic component renders a different tag depending on an `as` prop, and types its remaining props from whatever tag it was given. The pieces are `ValidComponent` (the constraint), `ComponentProps<T>` (the derived props), and `<Dynamic>` (the runtime renderer).

```tsx
import { splitProps } from "solid-js"
import { Dynamic } from "solid-js/web"
import type { ComponentProps, ValidComponent } from "solid-js"

type BoxProps<T extends ValidComponent> = {
  as?: T
} & ComponentProps<T>

function Box<T extends ValidComponent = "div">(props: BoxProps<T>) {
  // `as` is ours; everything else belongs to the underlying element.
  const [local, rest] = splitProps(props as BoxProps<ValidComponent>, ["as"])
  return <Dynamic component={local.as ?? "div"} {...rest} />
}

// Extra props are checked against the tag passed to `as`:
<Box as="a" href="/docs">Docs</Box>
<Box as="button" type="submit" onClick={submit}>Send</Box>
<Box>Plain div</Box>
// <Box as="button" href="/x" /> — error: href is not a button prop
```

Why each piece:

| Piece | Why |
|---|---|
| `T extends ValidComponent` | Accepts both intrinsic tags (`"a"`) and custom components. This is the same constraint `<Dynamic>` itself uses. |
| `ComponentProps<T>` | Resolves to `JSX.IntrinsicElements["a"]` for a tag, or the component's own props for a component. This is what makes `href` legal on `as="a"` and illegal on `as="button"`. |
| `<Dynamic component={…}>` | Swaps the rendered element **reactively**. A bare `props.as` in tag position would not update if `as` changed. |
| `splitProps` | Strips `as` while keeping `rest` a reactive proxy — a hand-built rest object would freeze every forwarded prop. → [Components & props](03-components-and-props.md) |

> **The `as ...` cast is expected.** `splitProps` cannot narrow a still-generic `T`, so widening to `BoxProps<ValidComponent>` inside the body is the standard escape hatch. The *call sites* stay fully type-checked, which is the point. Keep the cast internal; never widen the exported signature.

If the component only ever renders a fixed set of tags, skip the generic and use a union — it is simpler and needs no cast:

```tsx
type HeadingProps = { level: 1 | 2 | 3 } & ComponentProps<"h1">

function Heading(props: HeadingProps) {
  const [local, rest] = splitProps(props, ["level"])
  return <Dynamic component={`h${local.level}` as "h1" | "h2" | "h3"} {...rest} />
}
```

→ [`<Dynamic>`](04-control-flow.md) for the runtime behaviour, including what it renders when `component` is `undefined`.

---

## `splitProps` and `mergeProps`

### `splitProps` preserves reactivity and types as a tuple

```ts
import { splitProps } from "solid-js"
import type { ComponentProps } from "solid-js"

type ButtonProps = ComponentProps<"button"> & { loading?: boolean }

function Button(props: ButtonProps) {
  // Returns a typed tuple: [local, rest] where local has loading+children,
  // rest has everything else from ComponentProps<"button">
  const [local, rest] = splitProps(props, ["loading", "children"])
  //     ^────── { loading?: boolean, children: ... }
  //                     ^────── Omit<ButtonProps, "loading"|"children">

  return <button {...rest}>{local.loading ? "…" : local.children}</button>
}
```

❌ Never destructure props directly — it breaks reactivity:
```ts
// ❌ Destructuring reads values immediately; they become stale strings.
function Bad({ label, onClick }: { label: string; onClick: () => void }) {
  return <button onClick={onClick}>{label}</button>
}

// ✅ Access props inline or via splitProps
function Good(props: { label: string; onClick: () => void }) {
  return <button onClick={props.onClick}>{props.label}</button>
}
```

### `mergeProps` for default values

```ts
import { mergeProps } from "solid-js"

type Props = { color?: string; size?: number }

function Dot(props: Props) {
  // Provide reactive defaults without mutating props
  const merged = mergeProps({ color: "blue", size: 8 }, props)
  return (
    <circle
      fill={merged.color}
      r={merged.size}
    />
  )
}
```

`mergeProps` returns a reactive proxy where each property is read from the first argument that provides it (right-hand props win). The type is inferred as the intersection of all merged objects.

---

## Refs

### Local ref

```ts
let el: HTMLDivElement | undefined

// Solid assigns the element to `el` during mount (synchronously during JSX eval)
<div ref={el}>content</div>

// After mount, `el` is defined — but TypeScript doesn't know that.
// Use non-null assertion only after mount (e.g., inside onMount or effects).
createEffect(() => {
  console.log(el!.offsetWidth)
})
```

A more precise pattern — the `ref` callback:

```ts
let el!: HTMLDivElement    // definite assignment assertion

<div ref={el}>content</div>
// TypeScript now treats `el` as HTMLDivElement (not undefined)
// after the JSX assignment. This is idiomatic Solid.
```

### The `Ref<T>` type for forwarding

When a component needs to forward a ref to a DOM element, use `Ref<T>` in the props type. `Ref<T>` is `T | ((el: T) => void)`, which covers both the direct variable form and the callback form.

```ts
import type { Ref } from "solid-js"

type InputProps = {
  ref?: Ref<HTMLInputElement>
  placeholder?: string
}

function FancyInput(props: InputProps) {
  return <input ref={props.ref} placeholder={props.placeholder} />
}

// Parent using direct variable form:
let inputEl!: HTMLInputElement
<FancyInput ref={inputEl} />

// Parent using callback form:
<FancyInput ref={(el) => { someStore.setInput(el) }} />
```

---

## Stores

```ts
import { createStore } from "solid-js/store"
import type { Store, SetStoreFunction } from "solid-js/store"

type AppState = {
  user: { name: string; age: number } | null
  items: string[]
}

// createStore<T>() returns [Store<T>, SetStoreFunction<T>]
const [state, setState] = createStore<AppState>({
  user: null,
  items: [],
})
//    ^─── Store<AppState>    ^─── SetStoreFunction<AppState>

// Store<T> is a deep readonly proxy — fine-grained tracking on every property
state.user?.name    // string | undefined, fully typed

// SetStoreFunction<T> supports path-based updates
setState("user", "name", "Lorenzo")
setState("items", items => [...items, "new item"])
setState({ user: { name: "Lorenzo", age: 30 } })
```

### Sharing store type without the setter

When passing a store through context or props, pass `Store<T>` for read-only access and `SetStoreFunction<T>` separately if mutation is needed.

```ts
type Context = {
  state: Store<AppState>
  setState: SetStoreFunction<AppState>
}
```

---

## Resources

```ts
import { createResource } from "solid-js"
import type { Resource } from "solid-js"

// createResource<T>() — no source signal
const [user, { refetch, mutate }] = createResource<User>(fetchCurrentUser)
//     ^──── Resource<User>

// createResource<T, S>() — with a source signal (refetches when source changes)
const [userId, setUserId] = createSignal<number>(1)
const [post, { refetch }] = createResource(userId, fetchPostById)
//     ^──── Resource<Post>

// Resource<T> shape:
// - resource()          → T | undefined
// - resource.loading    → boolean
// - resource.error      → any
// - resource.state      → "unresolved" | "pending" | "ready" | "refreshing" | "errored"
// - resource.latest     → T | undefined (last resolved value, even while refreshing)

function UserCard(props: { userId: Accessor<number> }) {
  const [user] = createResource(props.userId, id => fetch(`/users/${id}`).then(r => r.json()) as Promise<User>)

  return (
    <Show when={user()} fallback={<p>{user.loading ? "Loading…" : "Error"}</p>}>
      {(u) => <p>{u().name}</p>}
    </Show>
  )
}
```

---

## Context

### The non-undefined pattern

`createContext<T>()` with no default value produces `Context<T | undefined>`. `useContext` then returns `T | undefined`, requiring callers to handle the undefined case everywhere. The standard solution is to wrap `useContext` in a custom hook that throws if the context is missing:

```ts
import { createContext, useContext } from "solid-js"
import type { Context } from "solid-js"

type ThemeContextValue = {
  theme: Accessor<string>
  setTheme: Setter<string>
}

// Without a default, the type is Context<ThemeContextValue | undefined>
const ThemeContext = createContext<ThemeContextValue>()

// The custom hook narrows out the undefined and provides a clear error.
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>")
  return ctx
}

// Provider component
export function ThemeProvider(props: ParentProps) {
  const [theme, setTheme] = createSignal("light")
  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {props.children}
    </ThemeContext.Provider>
  )
}
```

### Alternative: default value that always satisfies the type

```ts
// Provide a real default → no undefined in the type
const CounterContext = createContext({ count: () => 0, increment: () => {} })
// Type is Context<{ count: () => number; increment: () => void }> — no undefined
const ctx = useContext(CounterContext) // never undefined
```

Use this only when a meaningful "zero state" default makes sense. Prefer the custom hook pattern for contexts that genuinely require a Provider.

---

## Directives (`use:`)

Custom directives are Solid's mechanism for encapsulating DOM side effects. TypeScript needs to know about them via module augmentation.

```ts
// my-directive.ts
import type { Accessor } from "solid-js"

// The directive function: first arg is the element, second is an accessor of
// the value passed in JSX (e.g., use:tooltip="hello" → Accessor<string>)
export function tooltip(el: HTMLElement, value: Accessor<string>) {
  // set up a tooltip on `el` using `value()`
}

// Augment the Directives interface so JSX recognises use:tooltip
declare module "solid-js" {
  namespace JSX {
    interface Directives {
      tooltip: string   // the VALUE type, not the function type
    }
  }
}
```

```tsx
// In a component — no import type erasure issue as long as the directive
// function is referenced somewhere in the file.
import { tooltip } from "./my-directive"

// Prevent TS from erasing the import as unused:
// Either call tooltip somewhere, or use vite-plugin-solid with onlyRemoveTypeImports.
tooltip; // keep reference

<div use:tooltip="Click me to see the tooltip">...</div>
```

> **Import erasure gotcha.** TypeScript's `isolatedModules` mode removes imports it thinks are unused. Because `use:tooltip` in JSX is not a standard TS call-site, the import may be stripped. Set `{ "onlyRemoveTypeImports": true }` in your vite-plugin-solid config, or add a bare reference to the directive in the module body.

---

## Event handling

### `JSX.EventHandler<T, E>`

```ts
import type { JSX } from "solid-js"

// JSX.EventHandler<TElement, TEvent>
// - currentTarget is typed as TElement (the element the handler is on)
// - target is typed as EventTarget (less specific)
const handleInput: JSX.EventHandler<HTMLInputElement, InputEvent> = (e) => {
  console.log(e.currentTarget.value)  // string — currentTarget is HTMLInputElement
}

const handleClick: JSX.EventHandler<HTMLButtonElement, MouseEvent> = (e) => {
  console.log(e.currentTarget.dataset.id)
}
```

```tsx
// Inline — TypeScript infers the handler type from the JSX attribute
<input
  onInput={(e) => {
    // e.currentTarget → HTMLInputElement ✅
    console.log(e.currentTarget.value)
  }}
/>
```

### The `currentTarget` vs `target` gotcha

In DOM events, `target` is the element that originally dispatched the event (could be a descendant); `currentTarget` is the element the handler is registered on. Solid types `currentTarget` precisely from the element type in `JSX.EventHandler<T, E>`. TypeScript types `target` as `EventTarget & T` in some DOM lib versions, but you should always prefer `currentTarget` for reading input values.

```tsx
// ❌ target's type is less precise — may require casts
<input onInput={(e) => console.log((e.target as HTMLInputElement).value)} />

// ✅ currentTarget is exactly HTMLInputElement
<input onInput={(e) => console.log(e.currentTarget.value)} />
```

### Storing handlers with the right type

```ts
// When extracting a handler to a variable for reuse across elements,
// use the JSX attribute name's type helper or inline annotation:
type InputHandler = JSX.EventHandler<HTMLInputElement, InputEvent>

const onSearch: InputHandler = (e) => {
  setQuery(e.currentTarget.value)
}

<input onInput={onSearch} />
```

---

## `JSX.Element` vs `ValidComponent`

These are the two sides of JSX and they are easy to swap by mistake: `JSX.Element` is what a component **returns**, `ValidComponent` is what goes in the **tag position**.

| Type | Meaning |
|---|---|
| `JSX.Element` | Any value that can appear as a *child*: string, number, boolean, `null`, `undefined`, a DOM node, an array of those, or another component's output. Use it for `children` prop types and component return types. |
| `ValidComponent` | A tag name string (`"div"`) or a component function — the *left-hand side* of JSX. Use it when accepting a component or element type as a prop, and as the constraint on a polymorphic type parameter. |

```ts
import type { JSX, ValidComponent } from "solid-js"

// Accepting a component or tag as a prop
type Props = {
  as?: ValidComponent   // e.g. "section" or a custom component
  children: JSX.Element
}
```

> **There is no `JSX.ElementType` in Solid.** That is a React type. Solid's equivalent is `ValidComponent`, imported from `solid-js` (not from the `JSX` namespace). Likewise Solid has no `JSX.ElementNode` — the child type is just `JSX.Element`.

---

## A worked example: a typed, forwarding button

Bringing the patterns together:

```tsx
import { splitProps } from "solid-js"
import type { ComponentProps, Ref } from "solid-js"

type ButtonProps = ComponentProps<"button"> & {
  loading?: boolean
  ref?: Ref<HTMLButtonElement>
}

export function Button(props: ButtonProps) {
  const [local, rest] = splitProps(props, ["loading", "children", "ref"])

  return (
    <button
      ref={local.ref}
      {...rest}
      disabled={local.loading || rest.disabled}
      aria-busy={local.loading}
    >
      {local.loading ? <Spinner /> : local.children}
    </button>
  )
}

// Usage — both ref forms work
let btnEl!: HTMLButtonElement
<Button ref={btnEl} loading={saving()} onClick={handleSave}>Save</Button>
<Button ref={el => registerFocus(el)} type="submit">Submit</Button>
```

---

## See also

- [Mental model](01-mental-model.md) — why component functions run once, and what that means for typing
- [Reactivity](02-reactivity.md) — `createSignal`, `createMemo`, `createEffect` API details
- [Components and props](03-components-and-props.md) — `splitProps`, `mergeProps`, `children` helper
- [Stores](06-stores.md) — `createStore`, `produce`, `reconcile` in depth
