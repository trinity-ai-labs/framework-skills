# Control Flow

## Contents

- [Why control-flow components exist](#why-control-flow-components-exist)
- [`<Show>`](#show)
- [`<For>`](#for)
- [`<Index>`](#index)
- [`<For>` vs `<Index>` — decision table](#for-vs-index-decision-table)
- [`<Switch>` and `<Match>`](#switch-and-match)
- [`<Dynamic>`](#dynamic)
- [`<Portal>`](#portal)
- [`<ErrorBoundary>`](#errorboundary)
- [`<Suspense>` and `<SuspenseList>`](#suspense-and-suspenselist)
- [Nesting patterns](#nesting-patterns)
- [Import cheat-sheet](#import-cheat-sheet)
- [See also](#see-also)

---


Why Solid has dedicated control-flow components instead of plain JS expressions.

## Why control-flow components exist

In Solid a component runs **exactly once**. That means any JavaScript you write inside a component body — `if`, ternary, `.map()` — also runs exactly once at construction time. The DOM it produces is static from that point on; the condition can change but the DOM will not follow.

```tsx
// ❌ This ternary runs once. Flipping isAdmin() does nothing to the DOM.
function BadExample() {
  const [isAdmin, setIsAdmin] = createSignal(false)
  return <div>{isAdmin() ? <AdminPanel /> : <UserPanel />}</div>
}
```

The JSX expression `isAdmin() ? …` is evaluated when the component constructs, but it is not wrapped in any reactive computation that would re-run when `isAdmin` changes. So it stays frozen on whatever the initial value was.

Control-flow components fix this by putting the conditional or iteration logic **inside a reactive computation they own**. The component itself subscribes to the signals it depends on and surgically updates the DOM — mounting/unmounting children, moving nodes, or updating text — without tearing down and reconstructing the whole parent subtree.

```tsx
// ✅ <Show> subscribes to isAdmin() and mounts/unmounts the right child reactively.
function GoodExample() {
  const [isAdmin, setIsAdmin] = createSignal(false)
  return (
    <Show when={isAdmin()} fallback={<UserPanel />}>
      <AdminPanel />
    </Show>
  )
}
```

All control-flow components come from `"solid-js"` except `<Dynamic>` and `<Portal>`, which come from `"solid-js/web"`.

---

## `<Show>`

Conditionally renders its children. When `when` is falsy, renders `fallback` (or nothing).

### Signature

```ts
// Non-keyed (default): child callback receives Accessor<NonNullable<T>>
function Show<T>(props: {
  when: T | undefined | null | false
  keyed?: false
  fallback?: JSX.Element
  children: JSX.Element | ((item: Accessor<NonNullable<T>>) => JSX.Element)
}): JSX.Element

// Keyed: child callback receives NonNullable<T> directly
function Show<T>(props: {
  when: T | undefined | null | false
  keyed: true
  fallback?: JSX.Element
  children: JSX.Element | ((item: NonNullable<T>) => JSX.Element)
}): JSX.Element
```

Import: `import { Show } from "solid-js"`

### The callback-child form — type narrowing

When you pass a function as the child (instead of JSX directly), Solid passes the truthy `when` value into it. This narrows the type away from `T | null | undefined | false`.

```tsx
import { Show, createSignal } from "solid-js"

type User = { id: number; name: string }

function Profile() {
  const [user, setUser] = createSignal<User | null>(null)

  return (
    // Without keyed: item is Accessor<User>, call item() to read
    <Show when={user()} fallback={<p>Not logged in</p>}>
      {(item) => <p>Hello, {item().name}</p>}
    </Show>
  )
}
```

The accessor form (`item` is a getter) is the default (`keyed` omitted or `false`). Reading through `item()` keeps the value reactive — if `user()` changes to a different object while still truthy, `item()` will return the new value without unmounting/remounting the child.

### The `keyed` prop

```tsx
<Show when={user()} keyed>
  {(item) => <p>Hello, {item.name}</p>}
</Show>
```

With `keyed={true}`:
- `item` is the **value itself** (`User`), not an accessor — no need to call `item()`.
- Every change to the truthy `when` value (even if it stays truthy) destroys and recreates the child. This is the right choice when the child must reset its local state as the value changes — e.g., showing details for a different record.
- Use it sparingly; unnecessary destruction is expensive.

| | `keyed` omitted / `false` | `keyed={true}` |
|---|---|---|
| Child receives | `Accessor<NonNullable<T>>` — call `item()` | `NonNullable<T>` — use `item` directly |
| On truthy→truthy change | Child stays mounted; accessor returns new value | Child is destroyed and recreated |
| On falsy→truthy change | Child mounts | Child mounts |
| On truthy→falsy change | Child unmounts | Child unmounts |

### JSX children (no callback)

You can skip the callback entirely for simple cases — the `when` value is not threaded in, but the children still mount/unmount reactively:

```tsx
<Show when={isOpen()} fallback={<p>Panel closed</p>}>
  <ExpensivePanel />
</Show>
```

---

## `<For>`

Renders a list keyed by **item identity (reference)**. Rows are created, moved, or removed as items enter, leave, or change position in the array. The DOM node for an item follows that item when it moves.

### Signature

```ts
function For<T extends readonly any[], U extends JSX.Element>(props: {
  each: T | undefined | null | false
  fallback?: JSX.Element
  children: (item: T[number], index: Accessor<number>) => U
}): JSX.Element
```

Import: `import { For } from "solid-js"`

### Item and index

| Parameter | Type | Notes |
|---|---|---|
| `item` | `T[number]` (a **value**) | The item itself — read directly. |
| `index` | `Accessor<number>` (a **signal getter**) | Call `index()` to read the current position. Changes when items reorder — without destroying the row. |

`item` is a stable value because `<For>` identifies rows **by object identity**. When the same object reference stays in the array (even if it moves), `<For>` reuses its DOM node. When a new reference is added, a new row is created. When a reference is removed, its row is destroyed.

`index` being an accessor (not a plain number) means the row component can display `index()` reactively — when the item moves from position 2 to position 5, only the index accessor updates; the row is not recreated.

```tsx
import { For, createSignal } from "solid-js"

type Task = { id: number; title: string; done: boolean }

function TaskList() {
  const [tasks, setTasks] = createSignal<Task[]>([
    { id: 1, title: "Write tests", done: false },
    { id: 2, title: "Ship it", done: false },
  ])

  return (
    <ul>
      <For each={tasks()} fallback={<li>No tasks yet.</li>}>
        {(task, index) => (
          <li>
            {index() + 1}. {task.title}
          </li>
        )}
      </For>
    </ul>
  )
}
```

> **Note.** `<For>` is the right choice for every list that comes from Solid Query or a store: task lists, conversation threads, file trees, member rosters — any list of objects with stable identities. If a new batch of data arrives from a refetch, only new/removed items change; existing rows are untouched.

---

## `<Index>`

Renders a list keyed by **position**. The row at position `N` is always the same DOM node; when the array contents change, the `item` accessor at each position updates in place.

### Signature

```ts
function Index<T extends readonly any[], U extends JSX.Element>(props: {
  each: T | undefined | null | false
  fallback?: JSX.Element
  children: (item: Accessor<T[number]>, index: number) => U
}): JSX.Element
```

Import: `import { Index } from "solid-js"`

### Item and index

| Parameter | Type | Notes |
|---|---|---|
| `item` | `Accessor<T[number]>` (a **signal getter**) | Call `item()` to read the value at this position. Updates reactively when the value at this index changes. |
| `index` | `number` (a **plain number**) | Never changes — this row is always at position `index`. |

```tsx
import { Index, createSignal } from "solid-js"

function TemperatureTable() {
  const [readings, setReadings] = createSignal([72, 68, 75, 80])

  return (
    <table>
      <Index each={readings()}>
        {(value, i) => (
          <tr>
            <td>Sensor {i + 1}</td>
            <td>{value()} °F</td>
          </tr>
        )}
      </Index>
    </table>
  )
}
```

Here `i` is always `0`, `1`, `2`, `3`. When `setReadings([73, 68, 75, 80])` runs, only the `value` accessor at position 0 fires — one text node updates in place. No rows are created or destroyed.

---

## `<For>` vs `<Index>` — decision table

This is the most common mistake in Solid. Choose deliberately.

| Criterion | `<For>` | `<Index>` |
|---|---|---|
| **Keyed by** | Object identity (reference) | Array position |
| **`item` parameter** | Plain value (read directly) | Accessor — must call `item()` |
| **`index` parameter** | Accessor — must call `index()` | Plain number |
| **Row lifetime** | Tied to the object; survives reorder/insert | Tied to position; survives content-only change |
| **Insert / delete** | Only new/removed items change | All rows at or after the change position update |
| **Reorder** | DOM nodes move; rows are not recreated | All rows whose content changed update in place |
| **Local DOM state preserved** | Yes, on reorder (same object → same node) | Yes, for content changes; lost on insert/delete |
| **Best for** | Lists of objects (tasks, users, messages) — especially when items insert, delete, or reorder | Fixed-length arrays of primitives — form fields, sliders, sensor readings where focus/scroll state must survive value updates |

### The focus-loss trap with `<For>` on inputs

```tsx
// ❌ Using <For> for a list of text inputs.
// Inserting a new string at position 0 creates a new row at top —
// destroying the row at position 0 and making every `<input>` lose focus.
<For each={fieldValues()}>
  {(value) => <input value={value} />}
</For>

// ✅ <Index> for fixed-position inputs. The <input> at position N
// is the same DOM element; its value accessor updates without remounting.
<Index each={fieldValues()}>
  {(value, i) => <input value={value()} />}
</Index>
```

The root cause: `<For>` is identity-keyed — a new string literal `"hello"` is a different reference from the old one, so `<For>` always tears down and recreates input rows when their string values change. `<Index>` reuses the element at position N and just updates `value()`.

**Quick rule:** if your array items are **objects with stable identities** (have an `id`, are stored in a signal/store and mutated not replaced), use `<For>`. If your array items are **primitives** or objects that are replaced wholesale on each update, and the array length is roughly stable, use `<Index>`.

---

## `<Switch>` and `<Match>`

Multi-branch conditional — like a `switch` statement. The first `<Match when={...}>` whose `when` is truthy wins; the rest are skipped. If none match, `fallback` is rendered.

### Signature

```ts
function Switch(props: {
  fallback?: JSX.Element
  children: JSX.Element
}): JSX.Element

// MatchProps — the when/keyed/children interaction is the same as Show
type MatchProps<T> = {
  when: T | undefined | null | false
  keyed?: boolean
  children: JSX.Element | ((item: NonNullable<T> | Accessor<NonNullable<T>>) => JSX.Element)
}
function Match<T>(props: MatchProps<T>): JSX.Element
```

Import: `import { Switch, Match } from "solid-js"`

### Example

```tsx
import { Switch, Match, createSignal } from "solid-js"

type Status = "idle" | "loading" | "error" | "success"

function StatusBadge() {
  const [status, setStatus] = createSignal<Status>("idle")

  return (
    <Switch fallback={<span class="badge-unknown">Unknown</span>}>
      <Match when={status() === "idle"}>
        <span class="badge-idle">Idle</span>
      </Match>
      <Match when={status() === "loading"}>
        <span class="badge-loading">Loading…</span>
      </Match>
      <Match when={status() === "error"}>
        <span class="badge-error">Error</span>
      </Match>
      <Match when={status() === "success"}>
        <span class="badge-success">Done</span>
      </Match>
    </Switch>
  )
}
```

### Callback-child narrowing in `<Match>`

Just like `<Show>`, `<Match>` supports a callback child that receives the truthy value:

```tsx
type Result<T> = { ok: true; value: T } | { ok: false; error: string }

function ResultView(props: { result: Result<number> }) {
  return (
    <Switch>
      <Match when={props.result.ok && props.result}>
        {(r) => <p>Value: {r().value}</p>}
      </Match>
      <Match when={!props.result.ok && props.result}>
        {(r) => <p>Error: {r().error}</p>}
      </Match>
    </Switch>
  )
}
```

> **Note.** `<Switch>` evaluates `<Match when>` in order and stops at the first truthy one. Unlike JS `switch`, there is no fall-through.

---

## `<Dynamic>`

Renders a **component or HTML tag chosen at runtime**. The `component` prop accepts a string tag name (`"div"`, `"input"`) or a SolidJS component function. All other props are forwarded to the resolved component/element.

### Signature

```ts
// ValidComponent = string | Component | keyof JSX.IntrinsicElements
function Dynamic<T extends ValidComponent>(
  props: { component: T | undefined } & ComponentProps<T>
): JSX.Element
```

Import: `import { Dynamic } from "solid-js/web"`

```tsx
import { Dynamic } from "solid-js/web"
import { createSignal } from "solid-js"

const ICONS = {
  success: CheckIcon,
  error: XIcon,
  warning: WarningIcon,
} as const

type IconKind = keyof typeof ICONS

function StatusIcon(props: { kind: IconKind; class?: string }) {
  return (
    <Dynamic
      component={ICONS[props.kind]}
      class={props.class}
      aria-label={props.kind}
    />
  )
}
```

```tsx
// Rendering a native element chosen at runtime
function Heading(props: { level: 1 | 2 | 3; children: JSX.Element }) {
  return (
    <Dynamic component={`h${props.level}` as "h1" | "h2" | "h3"}>
      {props.children}
    </Dynamic>
  )
}
```

When `component` is `undefined`, `<Dynamic>` renders nothing. This is useful for nullable component slots.

---

## `<Portal>`

Renders its children into a **different part of the DOM** — outside the component's normal parent hierarchy. The rendered content is still part of Solid's reactive tree (signals, context, cleanup all work), but its DOM node is appended elsewhere.

### Signature

```ts
function Portal<T extends boolean = false, S extends boolean = false>(props: {
  mount?: Node           // Target DOM node. Defaults to document.body.
  useShadow?: T          // When true, mounts inside a shadow root (style isolation).
  isSVG?: S              // When true, the portal content is SVG (affects createElement calls).
  ref?: (el: HTMLDivElement | ShadowRoot) => void
  children: JSX.Element
}): void
```

Import: `import { Portal } from "solid-js/web"`

```tsx
import { Portal } from "solid-js/web"
import { createSignal, Show } from "solid-js"

function Modal(props: { title: string; children: JSX.Element; onClose: () => void }) {
  return (
    <Portal>
      {/* Rendered into document.body, above the app root in the DOM.
          Context (theme, i18n) flows in from the component tree. */}
      <div class="modal-backdrop" onClick={props.onClose}>
        <div class="modal-panel" onClick={(e) => e.stopPropagation()}>
          <h2>{props.title}</h2>
          {props.children}
          <button onClick={props.onClose}>Close</button>
        </div>
      </div>
    </Portal>
  )
}
```

### Custom mount point

```tsx
// Mount tooltip next to a specific container element
const tooltipRoot = document.getElementById("tooltip-root")!

function Tooltip(props: { text: string }) {
  return (
    <Portal mount={tooltipRoot}>
      <div class="tooltip">{props.text}</div>
    </Portal>
  )
}
```

> **Context flows in, not out.** Code inside `<Portal>` can call `useContext` and read signals defined in parent components — reactivity ownership follows the Solid tree, not the DOM tree. Only the rendered nodes land elsewhere in the DOM.

> **Cleanup is automatic.** When the component containing `<Portal>` unmounts, the portal's DOM nodes are removed from `mount`. No manual cleanup needed.

---

## `<ErrorBoundary>`

Catches errors thrown during **rendering or reactive updates** in its subtree and renders a fallback instead of a crashed UI.

### Signature

```ts
function ErrorBoundary(props: {
  fallback: JSX.Element | ((err: unknown, reset: () => void) => JSX.Element)
  children: JSX.Element
}): JSX.Element
```

Import: `import { ErrorBoundary } from "solid-js"`

### The `reset` function

The fallback callback receives two arguments:
- `err` — the caught error (typed `unknown`; cast or narrow as needed).
- `reset` — calling this clears the error and re-renders the children from scratch. Use it for "Try again" buttons.

```tsx
import { ErrorBoundary } from "solid-js"

function RiskySection() {
  return (
    <ErrorBoundary
      fallback={(err, reset) => (
        <div class="error-panel">
          <p>Something went wrong: {String(err)}</p>
          <button onClick={reset}>Try again</button>
        </div>
      )}
    >
      <DataFetcher />
    </ErrorBoundary>
  )
}
```

### What `<ErrorBoundary>` catches

- Errors thrown synchronously during the initial render of its children.
- Errors thrown inside reactive computations (`createEffect`, `createMemo`, reactive expressions in JSX) that run inside its subtree.
- Errors surfaced from `createResource` when they propagate through the render tree.

### What it does NOT catch

- Errors thrown inside event handlers (those are plain function calls, not reactive computations).
- Errors in asynchronous code that runs outside Solid's ownership tree (e.g., `setTimeout` callbacks without `runWithOwner`).

> **Nest multiple boundaries.** A single top-level `<ErrorBoundary>` is a safety net, but coarse-grained. Add boundaries around independent UI sections so a crash in the sidebar does not blank the whole app.

---

## `<Suspense>` and `<SuspenseList>`

These boundaries integrate with Solid's async system (`createResource`, `useTransition`). Full detail is in [07-async-and-resources.md](07-async-and-resources.md); here is the boundary-placement reference.

### `<Suspense>`

```ts
function Suspense(props: {
  fallback?: JSX.Element
  children: JSX.Element
}): JSX.Element
```

Import: `import { Suspense } from "solid-js"`

`<Suspense>` renders `fallback` whenever a **suspense-tracked async resource** inside its subtree is in a pending state. Once all resources resolve, the real children are shown.

```tsx
import { Suspense } from "solid-js"
import { createQuery } from "@tanstack/solid-query"

function UserProfile(props: { userId: string }) {
  return (
    <Suspense fallback={<Skeleton />}>
      {/* Any createResource or suspense-enabled primitive here
          will cause <Suspense> to show <Skeleton /> while loading. */}
      <ProfileDetails userId={props.userId} />
    </Suspense>
  )
}
```

Suspense is **non-blocking**: the reactive tree continues building inside; only the DOM reveal is deferred.

### `<SuspenseList>`

Coordinates **multiple sibling `<Suspense>` boundaries** to control the reveal order and prevent layout thrashing.

```ts
function SuspenseList(props: {
  revealOrder: "forwards" | "backwards" | "together"
  tail?: "collapsed" | "hidden"
  children: JSX.Element
}): JSX.Element
```

Import: `import { SuspenseList } from "solid-js"`

| `revealOrder` | Behaviour |
|---|---|
| `"forwards"` | Each boundary reveals once the previous one has resolved (left-to-right / top-to-bottom in source order). |
| `"backwards"` | Each boundary reveals once the next one has resolved (reverse order). |
| `"together"` | All boundaries reveal at the same time — wait for the slowest one. |

```tsx
import { Suspense, SuspenseList } from "solid-js"

function Dashboard() {
  return (
    <SuspenseList revealOrder="forwards" tail="collapsed">
      <Suspense fallback={<Skeleton />}>
        <SummaryCard />
      </Suspense>
      <Suspense fallback={<Skeleton />}>
        <ChartPanel />
      </Suspense>
      <Suspense fallback={<Skeleton />}>
        <ActivityFeed />
      </Suspense>
    </SuspenseList>
  )
}
```

> **`<SuspenseList>` is experimental** and does not have full SSR support. It is stable for client-side rendering in v1.9.x.

---

## Nesting patterns

Control-flow components nest freely. A common pattern:

```tsx
import { Show, For, Switch, Match, ErrorBoundary, Suspense } from "solid-js"

function TaskBoard() {
  const [filter, setFilter] = createSignal<"all" | "active" | "done">("all")
  const [tasks] = createResource(() => fetchTasks(filter()))

  return (
    <ErrorBoundary fallback={(err, reset) => <ErrorPanel error={err} onRetry={reset} />}>
      <Suspense fallback={<BoardSkeleton />}>
        <Show when={tasks()} fallback={<EmptyState />}>
          {(list) => (
            <For each={list()}>
              {(task) => (
                <Switch>
                  <Match when={task.kind === "bug"}>
                    <BugCard task={task} />
                  </Match>
                  <Match when={task.kind === "feature"}>
                    <FeatureCard task={task} />
                  </Match>
                  <Match when={true}>
                    <GenericCard task={task} />
                  </Match>
                </Switch>
              )}
            </For>
          )}
        </Show>
      </Suspense>
    </ErrorBoundary>
  )
}
```

---

## Import cheat-sheet

```ts
import {
  Show,
  For,
  Index,
  Switch,
  Match,
  ErrorBoundary,
  Suspense,
  SuspenseList,
} from "solid-js"

import { Dynamic, Portal } from "solid-js/web"
```

---

## See also

- [02-reactivity.md](02-reactivity.md) — why tracking matters and what "runs once" means for components
- [03-components-and-props.md](03-components-and-props.md) — the `children` helper, why you never destructure props
- [07-async-and-resources.md](07-async-and-resources.md) — `createResource`, `useTransition`, and full Suspense detail
- [15-pitfalls.md](15-pitfalls.md) — `.map()` in JSX, early returns that break control flow, and other gotchas
