# Refs and Directives

Accessing DOM elements directly, conditional classes, dynamic styles, prop spreading, and extending elements with custom behavior via `use:` directives.

---

## Contents

- [`ref` on elements](#ref-on-elements)
- [Forwarding refs through components](#forwarding-refs-through-components)
- [`classList` — conditional classes](#classlist-conditional-classes)
- [`style` — dynamic style objects](#style-dynamic-style-objects)
- [Spreads on elements](#spreads-on-elements)
- [`use:` custom directives](#use-custom-directives)
- [Wrapping an imperative third-party library](#wrapping-an-imperative-third-party-library)
- [`innerHTML` and `textContent`](#innerhtml-and-textcontent)
- [Namespaced bindings: `attr:`, `prop:`, `bool:`, `on:`](#namespaced-bindings-attr-prop-bool-on)
- [Cheat-sheet](#cheat-sheet)
- [See also](#see-also)


## `ref` on elements

Solid's `ref` gives you a handle to the underlying DOM node. There are two forms.

### Assignment form

```tsx
import { onMount } from "solid-js"

function AutoFocusInput() {
  let inputEl: HTMLInputElement  // declared; assigned by Solid during render

  onMount(() => {
    // The element exists here — it was created during render and
    // inserted into the DOM before onMount runs.
    inputEl.focus()
  })

  return <input ref={inputEl!} type="text" />
}
```

`ref={inputEl}` is syntactic sugar compiled by the Solid Babel transform. Solid assigns the created DOM element to the variable **synchronously, during the render pass**, before any `onMount` or `createEffect` callbacks fire. By the time `onMount` runs, `inputEl` is guaranteed to be a valid, in-DOM element.

> **TypeScript note.** The variable must be declared with `let`, not `const`. TypeScript sees it as possibly uninitialized (`HTMLInputElement | undefined`), so you need `inputEl!` at the ref site, or declare it with a definite assignment assertion: `let inputEl!: HTMLInputElement`.

### Callback form

```tsx
function MeasuredDiv() {
  let width = 0

  return (
    <div
      ref={(el) => {
        // el is the HTMLDivElement, assigned synchronously at element creation.
        // At this point the element exists but is NOT yet in the DOM —
        // use onMount if you need layout measurements.
        width = el.getBoundingClientRect().width  // 0 here; use onMount instead
      }}
    >
      Content
    </div>
  )
}
```

The callback form is useful when you want to run **immediate initialization** on the element (set a property, call a method that doesn't need layout) without declaring a variable. The callback fires at element-creation time — the same moment as the assignment form.

### Timing summary

| When | DOM element exists? | In DOM? | Layout available? |
|---|---|---|---|
| `ref=` assignment / callback fires | ✅ Yes | ❌ Not yet | ❌ No |
| `onMount` callback | ✅ Yes | ✅ Yes | ✅ Yes |
| `createEffect` (first run) | ✅ Yes | ✅ Yes | ✅ Yes |

```tsx
// ✅ Correct: use onMount for anything that needs the element in the DOM
function ScrollToBottom() {
  let containerEl!: HTMLDivElement

  onMount(() => {
    containerEl.scrollTop = containerEl.scrollHeight  // layout is ready
  })

  return <div ref={containerEl} class="scroll-container">{/* ... */}</div>
}
```

---

## Forwarding refs through components

When a wrapper component wants to expose its inner element to callers, pass the `ref` prop through. Solid compiles `ref` on a component to a **callback** internally, so the receiving component must wire it to an element.

```tsx
import { JSX, splitProps } from "solid-js"

// The Ref<T> utility type from solid-js
// type Ref<T> = T | ((el: T) => void)

type ButtonProps = JSX.ButtonHTMLAttributes<HTMLButtonElement> & {
  ref?: (el: HTMLButtonElement) => void
}

function PrimaryButton(props: ButtonProps) {
  const [local, rest] = splitProps(props, ["ref", "class", "children"])

  return (
    <button
      ref={local.ref}  // forward the callback to the underlying element
      class={`btn-primary ${local.class ?? ""}`}
      {...rest}
    >
      {local.children}
    </button>
  )
}

// Usage: the caller's variable gets assigned the inner <button> element
function Form() {
  let btnEl!: HTMLButtonElement

  onMount(() => btnEl.focus())

  return (
    <form>
      <PrimaryButton ref={btnEl}>Submit</PrimaryButton>
    </form>
  )
}
```

> **Why Solid uses callbacks internally for component refs.** A component can render multiple elements or conditionally render — Solid always calls the callback pattern at the framework level so the parent can receive any element the child chooses to expose.

---

## `classList` — conditional classes

`classList` accepts an object where keys are class names and values are boolean expressions. Solid compiles it to `element.classList.toggle(name, bool)` calls — only the classes whose boolean changes are touched.

```tsx
import { createSignal } from "solid-js"

function NavItem(props: { label: string; href: string; active: boolean }) {
  const [hovered, setHovered] = createSignal(false)

  return (
    <a
      href={props.href}
      class="nav-item"              // static base class; class + classList coexist
      classList={{
        "nav-item--active": props.active,   // reactive: updates when props.active changes
        "nav-item--hovered": hovered(),     // reactive: updates when hovered() changes
        "nav-item--disabled": false,        // never toggled
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {props.label}
    </a>
  )
}
```

`class` and `classList` can be used together on the same element — Solid merges them. The `class` attribute sets the initial class string; `classList` reactively toggles individual classes on top of it.

```tsx
// ❌ String concatenation — rebuilds the entire class string on every change
<div class={`item ${isActive() ? "active" : ""}`} />

// ✅ classList — surgically toggles only the changed class
<div class="item" classList={{ active: isActive() }} />
```

---

## `style` — dynamic style objects

The `style` attribute in Solid accepts either a **string** or an **object**. The object form is reactive — individual properties are set via `element.style.setProperty` rather than replacing the whole `style` attribute.

```tsx
import { createSignal } from "solid-js"

function ResizablePanel() {
  const [width, setWidth] = createSignal(300)

  return (
    <div
      style={{
        width: `${width()}px`,        // px must be included in the string value
        "background-color": "#f0f0f0", // kebab-case keys as strings
        "max-height": "80vh",
        "overflow-y": "auto",
      }}
    >
      Content
    </div>
  )
}
```

CSS property keys follow **kebab-case** in the object form (matching `element.style.setProperty`). You can also use camelCase, but kebab-case quoted strings are the idiomatic Solid style and match the CSS spec directly.

### CSS custom properties (variables)

```tsx
<div
  style={{
    "--theme-color": primaryColor(),
    "--spacing-base": `${spacing()}px`,
    color: "var(--theme-color)",
  }}
>
  Themed content
</div>
```

CSS custom properties work normally in the style object — Solid passes them through `element.style.setProperty("--theme-color", value)`.

```tsx
// ❌ Style string — not reactive; only sets the style once
<div style={`width: ${width()}px`} />

// ✅ Style object — each property updates reactively when its signal changes
<div style={{ width: `${width()}px` }} />
```

---

## Spreads on elements

You can spread an object of props onto an element. Solid handles spreads **reactively** — the spread is implemented as a reactive computation, so any reactive props in the object that change will update the element in place.

```tsx
import { mergeProps, splitProps, JSX } from "solid-js"

type InputProps = JSX.InputHTMLAttributes<HTMLInputElement> & {
  label?: string
}

function LabeledInput(props: InputProps) {
  // splitProps separates "our" props from "pass-through" props
  const [local, rest] = splitProps(props, ["label"])

  return (
    <label>
      {local.label}
      {/* rest still contains all HTML input attributes; spread forwards them */}
      <input {...rest} />
    </label>
  )
}
```

### Spread ordering and merging

When you combine a spread with explicit props, **last wins** for non-reactive attributes. For reactive props, each is tracked individually.

```tsx
// The explicit class="extra" comes after the spread, so it overrides
// whatever class was in otherProps
<div {...otherProps} class="extra" />

// The explicit class="extra" is inside the spread; otherProps.class wins
// (whichever is spread last wins)
<div class="extra" {...otherProps} />
```

Use `mergeProps` to safely merge with defaults before spreading — it preserves reactivity:

```tsx
function Button(props: ButtonProps) {
  // Merge in defaults; reactive values in props still update
  const merged = mergeProps({ type: "button" as const, disabled: false }, props)
  return <button {...merged} />
}
```

> **Never destructure props.** `const { class: cls, ...rest } = props` reads `class` once and freezes it. Use `splitProps` to keep reactivity alive.

---

## `use:` custom directives

Directives let you attach **reusable element behavior** that runs at element-creation time — autofocus, click-outside detection, drag-and-drop, tooltip wiring, etc. They are the Solid equivalent of Vue's `v-*` directives.

### Signature

A directive is a plain function with this signature:

```ts
(element: Element, accessor: Accessor<Value>) => void
```

- `element` — the DOM element the directive is applied to.
- `accessor` — a getter function (signal) that returns whatever value was passed to `use:directiveName`. Call `accessor()` inside a reactive computation to subscribe to changes.

The function is called **synchronously during element creation** (same timing as `ref`), before the element is in the DOM.

### Registration and use

A directive is just a function in scope — no registration step. Solid's Babel transform recognises `use:functionName` and calls `functionName(element, () => value)`.

```tsx
import { Accessor, onCleanup } from "solid-js"

// The directive function — exported so other files can import it
export function clickOutside(
  el: HTMLElement,
  accessor: Accessor<() => void>
) {
  const handler = (e: MouseEvent) => {
    if (!el.contains(e.target as Node)) {
      accessor()()  // accessor() returns the callback; call it
    }
  }

  document.addEventListener("click", handler)
  onCleanup(() => document.removeEventListener("click", handler))
}
```

```tsx
import { clickOutside } from "./directives"
import { createSignal } from "solid-js"

function Dropdown() {
  const [open, setOpen] = createSignal(false)

  return (
    <Show when={open()}>
      <div
        use:clickOutside={() => setOpen(false)}
        class="dropdown-panel"
      >
        <MenuItem>Option 1</MenuItem>
        <MenuItem>Option 2</MenuItem>
      </div>
    </Show>
  )
}
```

### TypeScript: `declare module` namespace augmentation

TypeScript does not know about `use:*` attributes by default — they are not part of JSX's standard intrinsic elements. You must declare each directive in the `JSX.Directives` interface:

```ts
// In the directive file (or a global .d.ts):
import "solid-js"

declare module "solid-js" {
  namespace JSX {
    interface Directives {
      // Key = directive name; Value = the type of the value passed to use:directiveName
      clickOutside: () => void
    }
  }
}
```

Without this, TypeScript errors on `use:clickOutside` with "Property 'clickOutside' does not exist on type 'JSX.IntrinsicElements'".

### The tree-shaking import gotcha

If you import a directive function and use it **only** as `use:directiveName` (no other direct call), TypeScript's `importsNotUsedAsValues: "error"` or aggressive tree-shaking may eliminate the import, breaking the directive silently.

```ts
// ❌ TypeScript may strip this import if it sees no explicit call to clickOutside
import { clickOutside } from "./directives"

// ✅ Option 1: use the babel-preset-typescript option onlyRemoveTypeImports: true
// ✅ Option 2: reference the identifier explicitly (no-op workaround)
import { clickOutside } from "./directives"
clickOutside  // keeps the import alive — evaluated but not called
```

The cleanest solution in a Vite/SolidStart project is to set `onlyRemoveTypeImports: true` in `babel-preset-typescript` (or the equivalent `@babel/plugin-transform-typescript` option), which stops TypeScript from removing any non-type imports.

### Full autofocus directive example

```ts
// directives/autofocus.ts
import { Accessor } from "solid-js"

// value is an optional boolean (default: focus always)
export function autofocus(el: HTMLElement, value: Accessor<boolean | undefined>) {
  if (value() !== false) {
    // requestAnimationFrame ensures the element is in the DOM
    requestAnimationFrame(() => el.focus())
  }
}

// TypeScript registration
declare module "solid-js" {
  namespace JSX {
    interface Directives {
      autofocus: boolean | undefined
    }
  }
}
```

```tsx
// Usage
import { autofocus } from "~/directives/autofocus"

function SearchBar() {
  return <input use:autofocus type="search" placeholder="Search…" />
}
```

---

## Wrapping an imperative third-party library

Chart libraries, CodeMirror/Monaco, map SDKs, drag-and-drop engines — anything that wants a real DOM node and manages its own subtree. The wrapper is always the same four moves, and each one maps to a Solid primitive:

| Move | Primitive | Why |
| --- | --- | --- |
| Get the node | `ref` | The element exists before `onMount`; `ref` hands it to you. |
| Construct once | `onMount` | The node is in the document by then, so libraries that measure layout work. |
| Push prop changes in | `createEffect` | One effect per independently-changing input, so a data change doesn't also re-run a theme change. |
| Tear down | `onCleanup` | Third-party instances hold listeners, observers and rAF loops that outlive the component otherwise. |

```tsx
import { onMount, onCleanup, createEffect } from "solid-js"
import Chart from "some-chart-lib"

function LineChart(props: { data: Point[]; theme: "light" | "dark" }) {
  let el!: HTMLDivElement
  let chart: Chart | undefined

  onMount(() => {
    chart = new Chart(el, { data: props.data, theme: props.theme })
    onCleanup(() => chart?.destroy())        // registered here, runs on unmount
  })

  // One effect per input. Each reads exactly one prop, so each fires only for
  // its own change — the component itself never re-runs.
  createEffect(() => chart?.setData(props.data))
  createEffect(() => chart?.setTheme(props.theme))

  return <div ref={el} />
}
```

The failure modes, in the order people hit them:

- **Constructing in the component body instead of `onMount`.** The `ref` is not assigned yet and the node is not in the document — libraries that read `offsetWidth` initialise at zero size.
- **One effect reading every prop.** It re-runs on any change and pushes all of them, which is how you get a chart that resets its zoom whenever the theme toggles. Split them.
- **Forgetting that the component never re-runs.** There is no re-render to sync state for you. If a prop is not read inside an effect, the library will never hear about it.
- **Destructuring props into the constructor** — `const { data } = props` freezes it, so the effects have nothing live to read. → [Pitfalls #1](15-pitfalls.md)
- **Returning the cleanup from `createEffect`.** Solid does not use React's return-a-cleanup convention; call `onCleanup(...)` inside the effect instead.

If the wrapper is generic enough to reuse across elements, express it as a [`use:` directive](#use-custom-directives) instead — same lifecycle, less boilerplate at the call site.

---

## `innerHTML` and `textContent`

Solid provides `innerHTML` and `textContent` as special props. They bypass the reactive DOM updates and set the property directly.

```tsx
// Render raw HTML — beware XSS; sanitize before use
<div innerHTML={sanitizedHtml()} />

// Set text content directly (faster than children for large text blobs)
<pre textContent={codeSnippet()} />
```

> **Security.** `innerHTML` is a vector for XSS. Always sanitize user-supplied HTML with a library like DOMPurify before passing it here. Solid does not sanitize for you.

---

## Namespaced bindings: `attr:`, `prop:`, `bool:`, `on:`

Solid provides prefix namespaces to override its default heuristic for mapping JSX attributes to DOM operations.

### `attr:*` — force attribute (string)

```tsx
// Forces setAttribute() instead of property assignment.
// Useful for Web Components and ARIA attributes that must be strings.
<my-web-component attr:data-count={count()} attr:aria-expanded={String(open())} />
```

### `prop:*` — force property assignment

```tsx
// Forces element[propName] = value.
// Useful for properties that hold non-string values (arrays, objects).
<video prop:srcObject={mediaStream()} />
<input prop:value={richObject()} />
```

Solid normally decides attribute vs property based on element type and prop name. `prop:` forces the property path even for names that would normally go through `setAttribute`.

### `bool:*` — boolean attribute

```tsx
// Adds the attribute (with empty string value) when truthy; removes it when falsy.
// Follows the HTML boolean attribute spec.
<button bool:disabled={isPending()} bool:aria-hidden={isHidden()}>Save</button>
```

Equivalent to `element.toggleAttribute(name, value)`.

### `on:*` — custom and non-bubbling events

The standard `onClick`, `onInput`, etc. are **delegated** (Solid attaches a single listener at the document root and dispatches by target). For custom events (from Web Components, `new CustomEvent(...)`) or events that do not bubble, use `on:`:

```tsx
function MyComponent() {
  return (
    <my-element
      on:customEvent={(e: CustomEvent<{ detail: string }>) => {
        console.log(e.detail)
      }}
      on:slotchange={(e) => console.log("slot changed", e)}
    />
  )
}
```

`on:*` attaches the listener **directly on the element** via `addEventListener`, with no delegation. This is required for:
- Custom events from Web Components that do not bubble.
- Events where you need the listener on the exact element (not the document root).
- Synthetic events from third-party libraries.

| Prefix | Compiled to | Use when |
|---|---|---|
| `onClick` / `onInput` etc. | Delegated listener at root | Standard bubbling DOM events |
| `on:eventName` | `el.addEventListener("eventName", …)` | Custom events, non-bubbling events, Web Components |
| `attr:name` | `el.setAttribute("name", value)` | Must be a string attribute (Web Components, ARIA) |
| `prop:name` | `el[name] = value` | DOM property that holds a non-string value |
| `bool:name` | `el.toggleAttribute("name", value)` | HTML boolean attributes |

---

## Cheat-sheet

```tsx
import { onMount, onCleanup, createSignal, splitProps, mergeProps, JSX } from "solid-js"

// --- ref forms ---
let el!: HTMLDivElement                         // assignment form
<div ref={el} />

<div ref={(el) => el.focus()} />               // callback form

// --- forwarding ---
function Wrapper(props: { ref?: (el: HTMLDivElement) => void }) {
  return <div ref={props.ref} />
}

// --- classList ---
<div class="base" classList={{ active: isActive(), disabled: isDisabled() }} />

// --- style object ---
<div style={{ "background-color": color(), width: `${w()}px` }} />

// --- spread + splitProps ---
const [local, rest] = splitProps(props, ["class"])
<input class={local.class} {...rest} />

// --- use: directive ---
<input use:autofocus />
<div use:clickOutside={() => setOpen(false)} />

// --- namespaced bindings ---
<video prop:srcObject={stream()} />
<my-el attr:data-id={id()} bool:disabled={disabled()} on:custom={handler} />
```

---

## See also

- [03-components-and-props.md](03-components-and-props.md) — `splitProps`, `mergeProps`, the `children` helper, why you never destructure
- [04-control-flow.md](04-control-flow.md) — `<Show>`, `<For>`, `<Portal>` — the boundary where refs first become available
- [05-lifecycle-and-ownership.md](05-lifecycle-and-ownership.md) — `onMount`, `onCleanup`, `createRoot`
- [14-typescript.md](14-typescript.md) — typing directives, `JSX.Element`, component generics
