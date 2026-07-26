---
name: solid
description: >-
  Use when writing, reading, debugging, or structuring SolidJS UI code (the `solid-js` library) or its
  ecosystem — signals/memos/effects (createSignal, createMemo, createEffect, on, untrack, batch),
  props reactivity (mergeProps, splitProps, the children helper, why you never destructure props),
  control flow (Show, For, Index, Switch/Match, Dynamic, Portal, ErrorBoundary, Suspense), stores
  (createStore, produce, reconcile), async (createResource, Suspense, transitions), context, refs &
  directives, @solidjs/router (Router, routes, params, preload/query/action), @tanstack/solid-query
  (createQuery/createMutation and the reactive options-function idiom), performance,
  @solidjs/testing-library, and TypeScript typing — and when a Solid value won't update, a list
  rebuilds every row and loses input focus, or an effect loops. Also for learning an API or laying
  out a Solid app. Targets Solid v1.9.x; SSR/SolidStart and Solid 2.0 are out of scope.
---

# SolidJS — the bible

A thorough, source-verified reference for **SolidJS v1.9.x** (the `solid-js` library) and its ecosystem (`@solidjs/router` v0.16.x, `@tanstack/solid-query` v5.x). Every API here was checked against the official docs and the published type definitions.

> **Scope.** Client-side Solid. **SSR and SolidStart are out of scope** — no file-based routing, no server functions / `"use server"`, no hydration guidance. **Solid 2.0 is out of scope**: it is a major rewrite that changes core primitives (effects, `Suspense`, `Index`, batching, stores, `use:` directives), and it is still prerelease on npm's `next` tag — everything here targets **1.9.x stable**. If you are on 2.x, treat this skill as historical.

**How to use this skill:** this file is the router. **Debugging something?** Jump straight to [Route by symptom](#something-is-broken-route-by-symptom) — you don't need to know which primitive is at fault. **Learning or building?** Read the short *mental model* and *how to think* sections below to orient, then open the one `reference/NN-*.md` file for the topic at hand. Each chapter is deep and standalone — don't load them all; load the one you need.

> **the reference app context.** Solid is the **frontend** — the Tauri desktop app's whole UI (`solid-js` + `@solidjs/router` + `@tanstack/solid-query` + Kobalte). **Effect is the sidecar** (the backend process); for that code reach for the separate **`effect-v3`** skill. App = Solid, sidecar = Effect. the reference app does **not** use `@effect-atom` in the app — server data flows through **Solid Query**, local UI state through **signals/stores**. → [Architecture](reference/16-architecture.md)
>
> This mapping is the *only* the reference app-specific routing rule in this skill. It lives here in the body rather than in the frontmatter description, because the description is injected into every session in every repo — and "Solid is the frontend, Effect is the sidecar" is true of the reference app, not of Solid. Projects that want the rule enforced up front should state it in their own `AGENTS.md` / `CLAUDE.md`.

---

## The 30-second mental model

Solid is **fine-grained reactivity with no virtual DOM**. A component is a **factory that runs exactly once** to create the DOM and wire up reactive subscriptions; it never re-runs. Only the specific reactive computations that read a changed value re-run — often updating a single text node or attribute directly.

- **Signals are getter/setter pairs.** `const [count, setCount] = createSignal(0)` — you read with the *function call* `count()`, not a bare variable. The call is what subscribes the surrounding computation.
- **Reactivity tracks function calls, not values.** Passing `count` (the getter) keeps it live; passing `count()` (the value) reads it once and freezes it. This is why **you never destructure props** — destructuring reads the value once and loses reactivity.
- **Three computations:** `createMemo` (cached derived value), `createEffect` (side effects after render), and the render itself. They auto-subscribe to every signal they call.
- **Control flow is components, not JS.** `<Show>`, `<For>`, `<Switch>` — because an `if` or `.map()` in JSX would run once and never update. They keep the DOM in sync efficiently (`<For>` is keyed by reference; `<Index>` is keyed by position).

```tsx
import { createSignal, createMemo, createEffect } from "solid-js"

function Counter() {
  const [count, setCount] = createSignal(0)        // signal: read count(), write setCount(n)
  const doubled = createMemo(() => count() * 2)    // derived, cached
  createEffect(() => console.log("count is", count())) // re-runs only when count() changes

  return <button onClick={() => setCount(c => c + 1)}>{count()} ({doubled()})</button>
}
// The component body runs ONCE. Clicking re-runs only the effect and the two text bindings —
// not the function. No VDOM diff, no re-render.
```

---

## How to think in Solid

1. **The component runs once; reactions run many times.** Put reactive reads inside JSX, memos, effects, or other tracked scopes — not in the one-time component body where they'd freeze. → [Mental model](reference/01-mental-model.md)
2. **Never destructure props or store fields.** `props.value` stays reactive; `const { value } = props` freezes it. Use `splitProps`/`mergeProps`, not spread/destructure. → [Components & props](reference/03-components-and-props.md)
3. **Derive, don't sync.** Reach for `createMemo` (or just an inline accessor `() => …`) before `createEffect`+`setSignal`. An effect that writes a signal to mirror another is almost always a memo. → [Reactivity](reference/02-reactivity.md)
4. **Use the framework's control flow.** `<For>`/`<Index>`/`<Show>`/`<Switch>` — never a raw `.map()` or ternary that needs to update. Pick `<For>` (keyed by item identity) vs `<Index>` (keyed by position) deliberately. → [Control flow](reference/04-control-flow.md)
5. **Deep reactive state is a store.** `createStore` gives per-property tracking and path/`produce`/`reconcile` updates; signals are for single values. → [Stores](reference/06-stores.md)
6. **Server state is Solid Query; local state is signals/stores.** Don't hand-roll caching/refetching in effects — `createQuery` owns it. The options go in a **function** so they stay reactive. → [Solid Query](reference/11-solid-query.md)

---

## Something is broken? Route by symptom

Most visits here are debugging, not learning. Match the symptom, then open the chapter.

| Symptom | Almost always | Go to |
| --- | --- | --- |
| Shows the first value, never updates | Destructured props/store, or a read in the run-once body | [15 §1–2](reference/15-pitfalls.md) |
| Branch never switches (spinner forever) | Early `return` instead of `<Show>` | [15 §3](reference/15-pitfalls.md) |
| List never updates, or every row rebuilds & inputs lose focus | `.map()` in JSX, or `<For>` vs `<Index>` picked wrong | [15 §4, §8](reference/15-pitfalls.md) · [04](reference/04-control-flow.md) |
| Whole list rebuilds **after a refetch**, though the data barely changed | New object refs replaced the ones the store/`<For>` tracked — needs `reconcile` | [15 §15](reference/15-pitfalls.md) · [06](reference/06-stores.md) |
| Infinite loop / value always one tick stale | `createEffect` used to derive — use `createMemo` | [15 §5](reference/15-pitfalls.md) |
| You added `untrack` to stop a loop, and now it never runs at all | `untrack` swallowed the trigger, not just the incidental read | [15 §17](reference/15-pitfalls.md) |
| A subtree tears down and rebuilds constantly | `<Show keyed>` re-keys on every value change | [15 §18](reference/15-pitfalls.md) |
| Callback/timer sees an old value | Stale closure over `x()` | [15 §7](reference/15-pitfalls.md) |
| Update lands a render late, or in an unpredictable order | A signal written from the component body or a memo | [15 §16](reference/15-pitfalls.md) |
| Store write does nothing | Direct mutation, or a new object replaced the tracked one | [15 §9, §15](reference/15-pitfalls.md) · [06](reference/06-stores.md) |
| Async effect runs once, or races | Tracking is lost after the first `await` | [15 §10](reference/15-pitfalls.md) |
| Effect fires on mount when you wanted change-only | Needs `on(dep, fn, { defer: true })` | [02](reference/02-reactivity.md) |
| Timer/listener keeps firing after unmount | Missing `onCleanup` | [15 §11](reference/15-pitfalls.md) |
| "computations created outside a `createRoot`" warning | No owner | [15 §13](reference/15-pitfalls.md) · [05](reference/05-lifecycle-and-ownership.md) |
| Forwarded attributes don't update | Hand-built spread object instead of a `splitProps` proxy | [15 §12](reference/15-pitfalls.md) |
| Server data is stale / double-fetching / hand-rolled cache | Should be Solid Query, not effects | [15 §14](reference/15-pitfalls.md) · [11](reference/11-solid-query.md) |

Not listed? Open [`15-pitfalls.md`](reference/15-pitfalls.md) — it is the full numbered index with a symptom→cause table at the end.

---

## Reference index — open the chapter you need

### Foundations
| Read this when you need… | File |
| --- | --- |
| Fine-grained reactivity, no VDOM, run-once components, the tracking model, why Solid | [`01-mental-model.md`](reference/01-mental-model.md) |
| `createSignal`/`createMemo`/`createEffect`, `on` (+ `defer`), `untrack`, `batch`, equality, ownership of reads; `createRenderEffect`/`createComputed`/`createReaction`; recipes for **debounce/throttle** and **`localStorage` persistence** | [`02-reactivity.md`](reference/02-reactivity.md) |
| Props reactivity, **never destructure**, `mergeProps`/`splitProps`, the `children` helper, `Component` types | [`03-components-and-props.md`](reference/03-components-and-props.md) |

### Rendering & lifecycle
| Read this when you need… | File |
| --- | --- |
| `Show`/`For`/`Index`/`Switch`/`Match`/`Dynamic`/`Portal`/`ErrorBoundary`/`Suspense` — and For vs Index | [`04-control-flow.md`](reference/04-control-flow.md) |
| `onMount`/`onCleanup`, `createRoot`, ownership, `getOwner`/`runWithOwner`, disposal, `createUniqueId`, and `render` — the app entry point | [`05-lifecycle-and-ownership.md`](reference/05-lifecycle-and-ownership.md) |

### State & async
| Read this when you need… | File |
| --- | --- |
| `createStore`, nested reactivity, path updates, `produce`, `reconcile`, `unwrap`, `createMutable` | [`06-stores.md`](reference/06-stores.md) |
| `createResource`, `Suspense`, `useTransition`/`startTransition`, `createDeferred`, `createSelector`, loading/error states, async patterns | [`07-async-and-resources.md`](reference/07-async-and-resources.md) |
| `createContext`/`useContext`, typed providers, scoping state to a subtree — and **sharing global state without it** (context vs a module-level signal vs a `createRoot` singleton) | [`08-context.md`](reference/08-context.md) |
| `ref`, forwarding refs, `use:` directives + custom directives, `classList`/`style`, spreads, `innerHTML`, the namespaced bindings `attr:`/`prop:`/`bool:`/`on:` (custom & non-bubbling events, web components), and **wrapping an imperative third-party library** (charts, editors, maps) | [`09-refs-and-directives.md`](reference/09-refs-and-directives.md) |

### Ecosystem
| Read this when you need… | File |
| --- | --- |
| **`@solidjs/router`** (v0.16): `Router`/`Route`, nested layouts, params & search params, `useNavigate`, `query`/`action`, route **`preload`**, `matchFilters`, `useBeforeLeave` (unsaved-changes guard), `MemoryRouter` (tests) | [`10-router.md`](reference/10-router.md) |
| **`@tanstack/solid-query`** (v5): `createQuery`/`createMutation`/`createInfiniteQuery`, the **options-function** idiom, keys, invalidation, the QueryClient | [`11-solid-query.md`](reference/11-solid-query.md) |

### Application
| Read this when you need… | File |
| --- | --- |
| Performance: where re-renders come from in Solid, keeping reactions narrow, memo boundaries, list perf, **list virtualization**, **`lazy()` code-splitting** | [`12-performance.md`](reference/12-performance.md) |
| Testing with `@solidjs/testing-library` + Vitest: rendering, `createRoot`, async, mocking providers | [`13-testing.md`](reference/13-testing.md) |
| TypeScript: typing components, props, signals/stores, refs, **generic components**, **polymorphic `as` props**, `JSX.Element` vs `ValidComponent` | [`14-typescript.md`](reference/14-typescript.md) |

### Cross-cutting
| Read this when you need… | File |
| --- | --- |
| **Anti-patterns & gotchas** — the numbered symptom→fix index: destructured props/stores, reads outside tracking, early returns, `.map()`/ternary in JSX, effect-as-derive, stale closures, For-vs-Index, direct store mutation, tracking lost after `await`, missing `onCleanup`, broken prop spreads, module-scope owners | [`15-pitfalls.md`](reference/15-pitfalls.md) |
| **How to structure a Solid app** — the Solid-app / Effect-sidecar boundary, the Solid Query data layer, providers, file layout | [`16-architecture.md`](reference/16-architecture.md) |

---

## Conventions in these docs

- Code targets **Solid v1.9.x**, `@solidjs/router` **v0.16.x**, `@tanstack/solid-query` **v5.x**. All examples use real imports (`import { createSignal, Show, For } from "solid-js"`).
- JSX uses Solid's attributes (`class` not `className`, `classList`, `onClick`, `ref`).
- `❌ don't / ✅ do` pairs flag the idiomatic choice — the most common ones are around props destructuring and reactivity loss.
- the reference app-specific notes are called out in blockquotes; the rest is framework-global.

## Verifying against source

When in doubt about an API, the source of truth is the official docs: <https://docs.solidjs.com> (Solid), <https://github.com/solidjs/solid-router> (router), <https://tanstack.com/query/latest/docs/framework/solid/overview> (Solid Query). To see how a pattern is used in your own app, grep for `createQuery`. Never guess an API name; confirm it exists.
