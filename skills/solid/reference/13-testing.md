# Testing Solid with `@solidjs/testing-library` + Vitest

> **When you reach for this:** you need to write unit or component tests for Solid code — render a component, exercise a hook, assert on reactive updates, drive async/Suspense, or isolate a component from a provider stack (auth, Solid Query) so it tests in a vacuum. This chapter is the testing counterpart to [Architecture](16-architecture.md): the same boundaries that make the app changeable are what make it testable.

The Solid testing story is small on purpose. There is **no re-render to wait for** — a Solid component runs once and then fine-grained reactions update the DOM directly. So "testing Solid" splits cleanly into two jobs:

1. **DOM-level component tests** — render real components, fire events, assert on the resulting DOM. This is `@solidjs/testing-library`, which wraps `@testing-library/dom`. It looks almost exactly like Testing Library anywhere else.
2. **Reactive-graph tests** — exercise signals/memos/effects or a hook *without* a component, by giving them a reactive root to live in. This is `renderHook`, `createRoot`, and `testEffect`.

Everything runs on **Vitest** with **jsdom**. The pieces:

| Tool | Version | Role |
| --- | --- | --- |
| `vitest` | 4.x | runner + assertions (`expect`) |
| `vite-plugin-solid` | 2.x | compiles JSX through Solid's Babel transform under test |
| `@solidjs/testing-library` | 0.8.x | `render`, `renderHook`, `cleanup`, `fireEvent`, queries |
| `@testing-library/jest-dom` | 6.x | DOM matchers (`toBeInTheDocument`, `toHaveAttribute`, …) |
| `@testing-library/user-event` | 14.x | realistic user interaction (optional; `fireEvent` is the lightweight path) |

---

## Contents

- [Vitest config for Solid](#vitest-config-for-solid)
- [`render` — component tests](#render-component-tests)
- [A real component test: isolating from props](#a-real-component-test-isolating-from-props)
- [Testing reactivity directly (no component)](#testing-reactivity-directly-no-component)
- [Async: `findBy*`, `waitFor`, Suspense](#async-findby-waitfor-suspense)
- [Mocking providers and context](#mocking-providers-and-context)
- [Testing Solid Query components — seed the cache](#testing-solid-query-components-seed-the-cache)
- [What to test, and what not to](#what-to-test-and-what-not-to)
- [Common pitfalls](#common-pitfalls)
- [See also](#see-also)


## Vitest config for Solid

The single thing you must get right is **the JSX transform**. Solid does not use a runtime JSX factory like React — `vite-plugin-solid` compiles JSX into direct DOM operations at build time, and the test build must run that same transform. Use `vite-plugin-solid` and the `jsdom` environment:

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config"
import solid from "vite-plugin-solid"

export default defineConfig({
  plugins: [solid()],
  test: {
    environment: "jsdom",
    globals: true,                       // so `describe/it/expect` are ambient (optional)
    setupFiles: ["./vitest.setup.ts"],   // jest-dom matchers + jsdom polyfills
  },
  resolve: {
    // Solid ships browser + server builds behind export conditions. Tests run
    // the browser build; `vite-plugin-solid` sets this for you, but if you hand-
    // roll resolution, the `"development"`/`"browser"` conditions matter.
    conditions: ["development", "browser"],
  },
})
```

```ts
// vitest.setup.ts
import "@testing-library/jest-dom/vitest"   // registers toBeInTheDocument(), etc.
```

> **A real-world setup.** The reference app runs two Vitest *projects* in one config: a `node` project for `*.test.ts` (lib/server logic, `environment: "node"`) and a `dom` project for `*.test.tsx` (components/hooks, `environment: "jsdom"`, `setupFiles: ["./vitest.setup.ts"]`). The split keeps fast pure-logic tests off jsdom. Its setup file also stubs jsdom gaps that mount-time code reaches for — `ResizeObserver`, `matchMedia`, `Element.prototype.scrollIntoView`, `EventSource` — so component tests don't fault on `X is not defined`. The split lives in `vitest.config.ts`, the stubs in `vitest.setup.ts`.

> **A Vite-8 wrinkle.** Newer Vite (bundled by Vitest 4) can route JSX through `oxc`, which reads `tsconfig.json`'s `jsx` setting. If your JSX comes out untransformed, pin the import source for the dom project (`oxc.jsx = { runtime: "automatic", importSource: "solid-js" }`) so `vite-plugin-solid`'s Babel transform still wins for Solid files. the reference app does exactly this because it also has React islands that need the opposite pragma.

---

## `render` — component tests

`render` takes a **function returning a component** (not the component itself — Solid needs to call it inside a reactive root), and returns the bound Testing Library queries plus a `container`/`unmount`/`asFragment`.

```tsx
import { render, screen, fireEvent, cleanup } from "@solidjs/testing-library"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Counter } from "./counter"

afterEach(cleanup)   // unmount + clear the document between tests

describe("Counter", () => {
  it("increments on click", () => {
    render(() => <Counter start={2} />)
    const button = screen.getByRole("button", { name: /count/i })
    expect(button).toHaveTextContent("count: 2")

    fireEvent.click(button)
    expect(button).toHaveTextContent("count: 3")   // no await — Solid updates synchronously
  })
})
```

Note the two Solid-specific facts a React habit gets wrong:

- **You pass `() => <Counter/>`, not `<Counter/>`.** The thunk is mandatory — `render` runs it inside a `createRoot` so the component's reactive scope (and `onCleanup`) is owned by the test.
- **There is no `rerender`.** A Solid component never re-renders. To change inputs over time, drive a **signal** the component reads, or re-`render` with new props from a fresh call. Updates from events/signals are applied **synchronously**, so most assertions need no `await`.

### Queries: prefer roles and test ids, in that order

Use the same query hierarchy as Testing Library everywhere: `getByRole` / `getByLabelText` (accessibility-anchored) first, then `getByText`, and `getByTestId` for structural anchors that have no good role.

| Variant | Found = 0 | Found = 1 | Found > 1 | Async |
| --- | --- | --- | --- | --- |
| `getBy*` | throws | element | throws | no |
| `queryBy*` | `null` | element | throws | no — use for *absence* assertions |
| `findBy*` | rejects | Promise<element> | rejects | yes — retries until present or times out |
| `getAllBy*` / `queryAllBy*` / `findAllBy*` | (see above) return arrays | | | |

```tsx
expect(screen.queryByText("Error")).not.toBeInTheDocument()   // assert absence with queryBy*
const row = await screen.findByTestId("project-row")          // wait for async appearance
```

> **Anchor assertions to test ids, not copy.** A test that asserts `getByText("Save changes")` breaks when a designer renames the button to "Save". A test that asserts `getByTestId("save-project")` survives the copy change and still fails loudly if the control disappears. the reference app's component tests lean on roles + stable test ids for exactly this reason — they're verifying *behavior and structure*, not marketing copy.

### `fireEvent` vs `user-event`

- `fireEvent` dispatches a single DOM event. Fast, synchronous, perfect for `click`, and `input` with `{ target: { value } }`. This is what most the reference app component tests use.
- `@testing-library/user-event` simulates a real user (focus, keydown/keyup, pointer events, IME) and is **async** — `await userEvent.click(el)`. Reach for it when the behavior depends on a realistic event sequence (typing into a combobox, tab order), not for a plain click.

```tsx
// fireEvent — input changes go through `target`
const input = screen.getByDisplayValue("Acme")
fireEvent.input(input, { target: { value: "Acme 2" } })
expect(props.onNameChange).toHaveBeenCalledWith("Acme 2")
```

```tsx
// user-event — realistic typing
import userEvent from "@testing-library/user-event"
const user = userEvent.setup()
await user.type(screen.getByRole("textbox"), "hello")
```

### `cleanup` is mandatory

Each `render` mounts into a fresh container appended to `document.body` and creates a reactive root. `cleanup()` unmounts every mounted tree (running `onCleanup`) and removes the containers. Call it in `afterEach` or you leak DOM and live effects across tests:

```tsx
import { cleanup } from "@solidjs/testing-library"
afterEach(cleanup)
```

> If you set `test.globals: true` **and** import from `@solidjs/testing-library`, cleanup is still your responsibility — Solid's library does not auto-register an `afterEach` the way some React setups do. Always wire `afterEach(cleanup)`.

---

## A real component test: isolating from props

The cleanest component tests take a **presentational component** and feed it props directly — no providers, no network. The component's job is "render these props, call these callbacks," and the test verifies exactly that.

```tsx
// project-details-card.test.tsx — the card is pure; the parent owns the data.
import { afterEach, describe, expect, it, vi } from "vitest"
import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library"
import { ProjectDetailsCard } from "./project-details-card"

afterEach(cleanup)

const PROJECT = { id: "p1", name: "Acme Logistics", description: "Shipping.", path: "/code/acme" }

function defaults(overrides = {}) {
  return {
    name: PROJECT.name,
    path: PROJECT.path,
    description: PROJECT.description,
    project: PROJECT,
    submitting: false,
    onNameChange: vi.fn(),
    onSaveField: vi.fn(),
    ...overrides,
  }
}

it("Save (name) is disabled when the name matches what's persisted (no-op write guard)", () => {
  render(() => <ProjectDetailsCard {...defaults()} />)
  const [saveName] = screen.getAllByRole("button", { name: /^save$/i })
  expect(saveName).toBeDisabled()
})

it("Save (name) sends a TRIMMED value", () => {
  const props = defaults({ name: "  Trimmed  " })
  render(() => <ProjectDetailsCard {...props} />)
  fireEvent.click(screen.getAllByRole("button", { name: /^save$/i })[0])
  expect(props.onSaveField).toHaveBeenCalledWith("name", "Trimmed")
})
```

This is the cheapest, most durable kind of UI test: no providers to mock because the component takes no context. When a component *does* reach for context or the query cache, you mock or seed — the next two sections.

---

## Testing reactivity directly (no component)

Signals, memos, and effects don't need a DOM. They need an **owner** — the reactive scope that tracks subscriptions and runs cleanups. Outside a component you create one explicitly. There are three tools.

### `renderHook` — the usual choice for hooks

`renderHook(hook, options?)` runs your hook inside a managed root and returns `{ result, owner, cleanup }`. `result` is whatever the hook returns (it stays a live reference — call its accessors to read current values).

```tsx
import { renderHook } from "@solidjs/testing-library"
import { describe, expect, it } from "vitest"
import { useCounter } from "./use-counter"

it("increments", () => {
  const { result } = renderHook(useCounter, { initialProps: [5] })
  expect(result.count()).toBe(5)      // result is the hook's return value
  result.increment()
  expect(result.count()).toBe(6)      // synchronous — read again after the setter
})
```

`options.initialProps` is the **argument array** passed to the hook. `options.wrapper` is a component that must **always return `props.children`** — that's how you inject providers (see below).

### `createRoot` — manual ownership for signals/memos/effects

When you want to test reactive primitives with no hook wrapper, wrap them in `createRoot(dispose => …)` and call `dispose()` when done. Inside the root, effects run and memos track:

```tsx
import { createRoot, createSignal, createMemo } from "solid-js"
import { expect, it } from "vitest"

it("memo derives from its source", () => {
  createRoot((dispose) => {
    const [n, setN] = createSignal(2)
    const doubled = createMemo(() => n() * 2)
    expect(doubled()).toBe(4)
    setN(5)
    expect(doubled()).toBe(10)   // memo recomputed on the source change
    dispose()                    // tear down the root, run cleanups
  })
})
```

> **Why a root at all?** A `createEffect`/`createMemo` created with no owner warns ("computations created outside a `createRoot` …") and never gets disposed. The root *is* the test's lifecycle. `renderHook` and `render` create one for you; `createRoot` is the bare-metal version.

### Observing effects: `createEffect` runs on a microtask

`createEffect` does **not** run synchronously on creation — it's scheduled. So you can't assert its side effect on the very next line; you have to let the scheduler flush. The robust pattern is `testEffect`, which resolves a promise *after* the effect has run and re-run:

```tsx
import { testEffect } from "@solidjs/testing-library"
import { createSignal, createEffect } from "solid-js"
import { expect, it } from "vitest"

it("effect observes each update", () =>
  testEffect((done) => {
    const [n, setN] = createSignal(0)
    const seen: number[] = []
    createEffect(() => {
      seen.push(n())
      if (n() === 2) done(seen)   // resolve once we've observed the final value
      else setN(n() + 1)          // drive the next run from inside the effect
    })
  }).then((seen) => expect(seen).toEqual([0, 1, 2])))
```

`testEffect` returns a promise you `await`/`return` from the test, and gives the effect a real owner so it actually runs. Use it whenever the thing under test is an **effect** rather than a pure derivation. For pure derivations, prefer a memo and assert synchronously (above) — that's the [derive-don't-sync](02-reactivity.md) rule showing up in tests.

---

## Async: `findBy*`, `waitFor`, Suspense

Anything that resolves on a microtask or a network tick needs an async assertion. Two tools:

- **`findBy*` queries** — retry the query until the element appears or a timeout elapses. The first choice for "this shows up after the fetch."
- **`waitFor(cb)`** — retry an arbitrary assertion callback until it passes. Use it when the condition isn't "an element exists" (e.g. "the mutation reports success", "this spy was called").

```tsx
import { render, screen, waitFor } from "@solidjs/testing-library"

it("shows the row once the resource resolves", async () => {
  render(() => <ProjectList />)             // <Suspense> shows a fallback first
  expect(screen.getByText("Loading…")).toBeInTheDocument()
  expect(await screen.findByTestId("project-row")).toBeInTheDocument()  // resolves post-fetch
})
```

Testing `Suspense` is just this: render, optionally assert the fallback, then `findBy*` the resolved content. Because Solid suspends on read of a pending `createResource`/Solid Query, you don't orchestrate the suspension — you just wait for the resolved DOM.

> `findBy*` is rarely needed for *synchronous* reactive updates — those land immediately. Reach for async queries specifically for Suspense, resources, transitions, and routing. If you find yourself `await`-ing a plain signal update, you've probably got a real async boundary you didn't realize was there.

---

## Mocking providers and context

A component that calls `useAuthContext()` (or any guarded `useX()`) throws outside its provider — by design (see [Context](08-context.md)). Tests have two ways to satisfy that dependency.

### Option A — `vi.mock` the provider module (isolate one context)

When you only need *one* piece of context and don't want the real provider's machinery (network calls, effects), mock the module so `useX()` returns a fixed value. This is the reference app's standard way to pin the active auth scope for a hook/component under test:

```tsx
// Mock BEFORE importing anything that pulls the provider in.
vi.mock("@/components/providers/auth", () => ({
  useAuthContext: () => ({
    activeScope: () => ({ type: "personal", teamId: null, accountId: "acc-test" }),
  }),
}))

import { useRemoveIdentity } from "./hosting"   // now sees the mocked useAuthContext
```

`vi.mock` is hoisted above imports, so it's in force before the module graph loads. The factory returns *only* the surface your code touches (`activeScope` here) — you're not rebuilding the whole provider, just the read the code makes. This is the test seam: swap the deep provider for a one-line stub at its public interface.

### Option B — `wrapper` (compose the real providers)

When you *want* the real provider (e.g. you're testing how a component reacts to a real `QueryClientProvider`), pass a `wrapper` to `render`/`renderHook`. The wrapper must always return `props.children`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query"
import type { JSX } from "solid-js"

function wrap(qc: QueryClient) {
  return (props: { children: JSX.Element }) => (
    <QueryClientProvider client={qc}>{props.children}</QueryClientProvider>
  )
}

renderHook(() => useProjects(), { wrapper: wrap(new QueryClient()) })
render(() => <ProjectList />, { wrapper: wrap(new QueryClient()) })
```

Nest wrappers when a component needs several providers — compose them into one wrapper component (`<ThemeProvider><QueryClientProvider>{props.children}…`). Most tests need only the one or two providers the component actually reads; don't reconstruct the whole app shell.

---

## Testing Solid Query components — seed the cache

This is the highest-leverage pattern for a Solid-Query app, and the reference app's bread and butter. Each query hook subscribes to a **scoped key** and fetches via `queryFn`. In a test you don't want to mock `fetch` or wait for a network call — you want the hook to behave as if a fetch already succeeded.

**Seed the cache.** Build a *fresh* `QueryClient` per test, `setQueryData(key, value)` for the exact key the hook subscribes to, and render under that client. The hook mounts, finds fresh data at its key, and skips the fetch entirely — a deterministic "successful fetch" with zero network.

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query"
import { render, screen, cleanup } from "@solidjs/testing-library"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { JSX } from "solid-js"
import { scopedKeys, toScopeArg } from "@/query/hooks/keys"
import { ProjectList } from "./project-list"

// Pin the scope the hook keys on, so we know which slot to seed.
vi.mock("@/components/providers/auth", () => ({
  useAuthContext: () => ({
    activeScope: () => ({ type: "personal", teamId: null, accountId: "acc-test" }),
  }),
}))

const SCOPE = toScopeArg({ type: "personal", teamId: null, accountId: "acc-test" })

// A throwaway client with retries off and staleTime 0 — predictable in tests.
function fresh() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
}
function wrap(qc: QueryClient) {
  return (p: { children: JSX.Element }) => (
    <QueryClientProvider client={qc}>{p.children}</QueryClientProvider>
  )
}

afterEach(cleanup)

it("renders the seeded projects without hitting the network", async () => {
  const qc = fresh()
  // SEED the exact scoped key the hook subscribes to == a successful fetch.
  qc.setQueryData(scopedKeys.projects(SCOPE), {
    projects: [{ id: "p1", name: "Acme" }],
    activeProjectId: "p1",
  })

  render(() => <ProjectList />, { wrapper: wrap(qc) })

  // testid-anchored: survives copy changes, fails loudly if the row vanishes.
  expect(await screen.findByTestId("project-row-p1")).toHaveTextContent("Acme")
})
```

Why this works: `scopedKeys.projects(SCOPE)` is the **same factory** the hook calls (`useProjects` builds its `queryKey` from `scopedKeys.projects(toScopeArg(scope))`). Seed via the registry, not a hand-typed array, and the seeded slot is guaranteed to match the slot the hook reads — keys can't drift out of sync. (the reference app's branded keys won't even *compile* a bare array through `setQueryData`; the registry is the only door.)

### Testing cache effects without a component

Many "Solid Query" behaviors are pure cache operations — an SSE handler invalidates a key, a mutation patches a slot. Those test against a bare `QueryClient`, no rendering at all:

```tsx
import { QueryClient } from "@tanstack/solid-query"
import { describe, expect, it } from "vitest"
import { applyPresenceUpdate } from "../sse"
import { scopedKeys, toScopeArg } from "./keys"

const SCOPE = toScopeArg({ type: "personal", teamId: null, accountId: "acc-test" })
const fresh = () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })

it("an offline event drops the user's rows in place (no refetch)", () => {
  const qc = fresh()
  const key = scopedKeys.presence(SCOPE)
  qc.setQueryData(key, { online: [{ user_id: "a" }, { user_id: "b" }] })

  applyPresenceUpdate(qc, SCOPE, { userId: "a", status: "offline" })

  expect(qc.getQueryData(key)).toEqual({ online: [{ user_id: "b" }] })
  expect(qc.getQueryState(key)?.fetchStatus).toBe("idle")   // setData, not a refetch
})
```

The useful `QueryClient` introspection in tests:

| Call | Tells you |
| --- | --- |
| `qc.getQueryData(key)` | the current cached value |
| `qc.getQueryState(key)?.isInvalidated` | whether the slot was busted (precise, independent of `staleTime`) |
| `qc.getQueryState(key)?.dataUpdateCount` | bumped on every `setQueryData` — proves a write happened |
| `qc.getQueryState(key)?.fetchStatus` | `"idle"` means no refetch was triggered |
| `qc.getQueryCache().find({ queryKey })` | the raw query, for fine-grained assertions |

Assert `isInvalidated` rather than "was refetched" — it's the exact "this got busted" flag and doesn't depend on whether a network actually fired. To test a mutation's invalidation, seed the affected keys, run the mutation (via `renderHook`), `await waitFor(() => expect(result.isSuccess).toBe(true))`, then check `isInvalidated` on each key:

```tsx
const { result } = renderHook(() => useRemoveIdentity(), { wrapper: wrap(qc) })
result.mutate({ accountId: "acct_1", host: "github.com" })
await waitFor(() => expect(result.isSuccess).toBe(true))
expect(qc.getQueryCache().find({ queryKey: scopedKeys.gitIdentities(SCOPE) })?.state.isInvalidated)
  .toBe(true)
```

---

## What to test, and what not to

- ✅ **Behavior and structure** — does clicking Save call the callback with the right value? Does the seeded data render in the right row? Is the disabled state correct? Anchor to roles/test ids.
- ✅ **Pure cache reducers** — invalidation/setData logic against a bare `QueryClient`. Fast, no DOM.
- ✅ **Hook contracts** — `renderHook` + seeded cache or mocked context.
- ❌ **Implementation details** — don't assert on internal signal names, class names that are styling-only, or the order of memo recomputation. Those churn without behavior changing.
- ❌ **The framework** — don't test that `createMemo` caches or `<For>` is keyed. That's Solid's job; trust it.
- ❌ **Copy** — don't anchor assertions to user-facing strings that a writer will rephrase. Use test ids.

> **Testability is a design signal.** If a component is painful to test because it reaches into five providers and does its own fetching, that's the [architecture](16-architecture.md) telling you to split it: lift the data into a hook, make the view presentational, and the test becomes "render props, assert DOM." A hard-to-test component is usually a mis-placed boundary, not a hard-to-test framework.

---

## Common pitfalls

❌ `render(<Comp />)` — passing the element. Solid needs the thunk.
✅ `render(() => <Comp />)`.

❌ Forgetting `afterEach(cleanup)` — DOM and live effects leak across tests, causing flaky cross-talk.
✅ Always `afterEach(cleanup)`.

❌ Asserting an effect's side effect on the next synchronous line — `createEffect` is scheduled, not immediate.
✅ Use `testEffect`, or `await waitFor(...)`.

❌ Creating signals/effects with no owner (bare, outside any root) — they warn and never dispose.
✅ Wrap in `createRoot(dispose => …)`, or use `renderHook`/`render`.

❌ Seeding the cache with a hand-typed key array that drifts from what the hook builds.
✅ Seed via the same key factory the hook uses (`scopedKeys.x(scope, …)`).

❌ Sharing one module-level `QueryClient` across tests — leaked cache state makes order-dependent failures.
✅ A `fresh()` client per test.

❌ Reaching for `user-event` (async, heavy) for a plain click.
✅ `fireEvent.click(el)` for single events; `user-event` only when a realistic sequence matters.

---

## See also

- [Reactivity](02-reactivity.md) — derive-don't-sync; why effects schedule and memos don't
- [Components & props](03-components-and-props.md) — why `render(() => …)` and never destructure props
- [Context](08-context.md) — the guarded `useX()` pattern these tests mock
- [Solid Query](11-solid-query.md) — keys, the options-function idiom, `setQueryData`/invalidation
- [Lifecycle & ownership](05-lifecycle-and-ownership.md) — `createRoot`, disposal, owners
- [Architecture](16-architecture.md) — the boundaries that make all of this testable
- Solid Testing Library: <https://github.com/solidjs/solid-testing-library> · Testing Library: <https://testing-library.com>
