# Async & Resources

`createResource`, `<Suspense>`, transitions, and the async model.

## The two layers of async state in the reference app

| Layer | Primitive | Use when |
|---|---|---|
| **Server / shared data** | `@tanstack/solid-query` (`createQuery`) | Fetching server state that is cached, deduplicated, shared across components, and refetched on focus/interval |
| **Local / one-off async** | `createResource` | A single async value driven by local signal state, not needing the query cache — e.g., an initial config load, a file read, a derived async computation |

`createResource` is Solid's built-in primitive. Solid Query (`createQuery`) builds a full caching and lifecycle layer on top of it. Both integrate with `<Suspense>` the same way. For the reference app server data, the chapter to read is [11-solid-query.md](11-solid-query.md); this chapter covers the primitive that underpins everything.

---

## Contents

- [The two layers of async state in the reference app](#the-two-layers-of-async-state-in-the-reference-app)
- [`createResource` — the primitive](#createresource-the-primitive)
- [Basic example](#basic-example)
- [Source signal — reactive fetching](#source-signal-reactive-fetching)
- [The fetcher's second argument — `info`](#the-fetchers-second-argument-info)
- [`mutate` and `refetch`](#mutate-and-refetch)
- [`<Suspense>` — coordinated loading boundaries](#suspense-coordinated-loading-boundaries)
- [`<ErrorBoundary>` — catching resource errors](#errorboundary-catching-resource-errors)
- [Multiple resources under one `<Suspense>`](#multiple-resources-under-one-suspense)
- [`<SuspenseList>` — ordered reveal](#suspenselist-ordered-reveal)
- [`useTransition()` / `startTransition()` — no-flash navigation](#usetransition-starttransition-no-flash-navigation)
- [`createDeferred` — low-priority derived value](#createdeferred-low-priority-derived-value)
- [`createSelector` — O(1) active-item tracking](#createselector-o1-active-item-tracking)
- [`initialValue` option — avoid the `undefined` flash](#initialvalue-option-avoid-the-undefined-flash)
- [`onHydrated` option — SSR hydration callback](#onhydrated-option-ssr-hydration-callback)
- [Worked example — profile page with loading, error, and refresh](#worked-example-profile-page-with-loading-error-and-refresh)
- [Positioning — when to use what](#positioning-when-to-use-what)
- [See also](#see-also)


## `createResource` — the primitive

```ts
import { createResource } from "solid-js"
```

### Overload 1 — fetcher only (no source signal)

```ts
const [data, { mutate, refetch }] = createResource(fetcher, options?)
```

Fetches immediately on mount. The fetcher receives `(true, { value, refetching })`.

### Overload 2 — source signal drives refetch

```ts
const [data, { mutate, refetch }] = createResource(source, fetcher, options?)
```

- `source` — a reactive accessor (`() => string`), or a static value, or any falsy value. When source returns falsy (`null`, `false`, `undefined`, `0`, `""`), the fetch is **skipped** — the resource stays in the `"unresolved"` state. When source becomes truthy, the fetch runs. This is the **conditional-fetch pattern**.
- `fetcher` — `(sourceValue: S, info: { value: T | undefined, refetching: R | boolean }) => T | Promise<T>`
- `options` — `{ initialValue?, name?, storage?, onHydrated? }`

### Types: what `data` is

`data` is both a **function** (calling it returns the current value) and an **object** with reactive properties:

```ts
type Resource<T> =
  | { state: "unresolved"; loading: false; error: undefined; (): undefined }
  | { state: "pending";    loading: true;  error: undefined; (): undefined }
  | { state: "ready";      loading: false; error: undefined; latest: T; (): T }
  | { state: "refreshing"; loading: true;  error: undefined; latest: T; (): T }
  | { state: "errored";    loading: false; error: any;       (): never }
```

| Property | Type | Notes |
|---|---|---|
| `data()` | `T \| undefined` | Call the accessor to read the value; subscribes to changes |
| `data.state` | `"unresolved" \| "pending" \| "ready" \| "refreshing" \| "errored"` | Discrete state machine |
| `data.loading` | `boolean` | `true` in `pending` and `refreshing` states |
| `data.error` | `any` | Set only in `errored` state |
| `data.latest` | `T \| undefined` | Like `data()` but does NOT throw to Suspense in `refreshing` state — shows the stale value |

### State transitions

```
unresolved → pending → ready
                     ↘ errored
             ready → refreshing → ready
                               ↘ errored
```

---

## Basic example

```tsx
import { createResource } from "solid-js"

async function fetchUser(id: number) {
  const res = await fetch(`/api/users/${id}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<{ id: number; name: string; email: string }>
}

const USER_ID = 42

function UserCard() {
  const [user] = createResource(() => fetchUser(USER_ID))

  // Calling user() inside JSX hooks into Suspense above this component
  return <div>{user()?.name}</div>
}
```

---

## Source signal — reactive fetching

When the data to fetch depends on a signal, pass the signal as `source`. The resource re-fetches automatically when the source changes.

```tsx
import { createSignal, createResource } from "solid-js"

async function searchUsers(query: string) {
  const res = await fetch(`/api/users?q=${encodeURIComponent(query)}`)
  return res.json() as Promise<{ id: number; name: string }[]>
}

function UserSearch() {
  const [query, setQuery] = createSignal("")

  // Re-fetches every time query() changes (and query is truthy)
  const [results] = createResource(query, searchUsers)

  return (
    <div>
      <input
        value={query()}
        onInput={(e) => setQuery(e.currentTarget.value)}
        placeholder="Search users…"
      />
      {/* results() reads inside JSX — Suspense above shows fallback while loading */}
      <pre>{JSON.stringify(results(), null, 2)}</pre>
    </div>
  )
}
```

### Conditional fetch — falsy source skips the fetch

```tsx
import { createSignal, createResource, Show } from "solid-js"

function ConditionalFetch() {
  const [userId, setUserId] = createSignal<number | null>(null)

  // Source is () => userId() — when userId() is null (falsy), fetch is skipped
  const [user] = createResource(
    () => userId() ?? false,  // explicitly falsy when no id
    (id) => fetch(`/api/users/${id}`).then(r => r.json())
  )

  return (
    <div>
      <button onClick={() => setUserId(1)}>Load user 1</button>
      <Show when={userId()}>
        <div>{user()?.name}</div>
      </Show>
    </div>
  )
}
```

> **Rule:** `source` must return a truthy value for the fetch to run. A falsy source (`null`, `false`, `undefined`) leaves the resource in `"unresolved"` — no network request is made. This is the idiomatic way to do conditional fetching in Solid. No need for guard `if` statements inside the fetcher.

---

## The fetcher's second argument — `info`

```ts
type ResourceFetcherInfo<T, R> = {
  value: T | undefined   // the previous/current value before refetch
  refetching: R | boolean  // true if triggered by refetch(); the arg passed to refetch(arg) if any
}
```

```ts
const [data] = createResource(source, async (src, { value, refetching }) => {
  // value — the result from the previous successful fetch (for optimistic display)
  // refetching — true when refetch() was called without arg; the arg when refetch(myArg) was called

  if (refetching === "background") {
    // Called as refetch("background") — do a quiet poll
    const delta = await fetchDelta(src, value)
    return applyDelta(value, delta)
  }

  return fetchFull(src)
})
```

---

## `mutate` and `refetch`

`createResource` returns `[data, { mutate, refetch }]`.

### `mutate` — local override without fetching

Sets the resource value directly, bypassing the fetcher. Useful for optimistic updates or local patching.

```ts
const [user, { mutate, refetch }] = createResource(userId, fetchUser)

// Optimistic name change
function updateName(newName: string) {
  mutate((prev) => prev ? { ...prev, name: newName } : prev)
  // fire-and-forget API call; if it fails, call refetch() to re-sync
  api.updateUser({ name: newName }).catch(() => refetch())
}
```

`mutate` has the same signature as a signal setter: `mutate(value)` or `mutate(prev => next)`.

### `refetch` — re-run the fetcher

```ts
// Re-run with the current source value
refetch()

// Re-run and pass a value to the fetcher's info.refetching
refetch("force")
```

```tsx
function UserCard() {
  const [user, { refetch }] = createResource(userId, fetchUser)

  return (
    <div>
      <span>{user()?.name}</span>
      <button onClick={() => refetch()}>Refresh</button>
    </div>
  )
}
```

---

## `<Suspense>` — coordinated loading boundaries

Reading a `pending` resource inside JSX throws a Promise (internally). `<Suspense>` catches these throws and shows its `fallback` until **all** resources in its subtree have resolved.

```tsx
import { Suspense } from "solid-js"

function App() {
  return (
    <Suspense fallback={<div>Loading…</div>}>
      <UserProfile />   {/* reads user() */}
      <UserPosts />     {/* reads posts() */}
    </Suspense>
  )
}
```

Both `user()` and `posts()` can be pending at the same time. The fallback stays until both resolve. Once resolved, the children render. If either resource re-enters `refreshing` after already being `ready`, `<Suspense>` does NOT re-show the fallback — it keeps the existing UI visible (the "refreshing" state is distinct from "pending" for this reason). Use `data.loading` to show a local spinner during refreshes.

```tsx
function UserProfile() {
  const [user] = createResource(userId, fetchUser)

  return (
    <div>
      {/* data.latest keeps the old value during refreshing; avoids Suspense flicker */}
      <h1>{user.latest?.name ?? user()?.name}</h1>
      {user.loading && <span class="spinner" />}
    </div>
  )
}
```

### `<Suspense>` props

```tsx
<Suspense fallback={<SkeletonCard />}>
  {/* children */}
</Suspense>
```

`fallback` is any `JSX.Element` — rendered when any child resource is in `"pending"` state.

---

## `<ErrorBoundary>` — catching resource errors

When `data()` is called while the resource is in `"errored"` state inside a tracking scope, it **throws** the error to the nearest `<ErrorBoundary>`. Combine `<ErrorBoundary>` outside (or around) `<Suspense>`:

```tsx
import { ErrorBoundary, Suspense } from "solid-js"

function App() {
  return (
    <ErrorBoundary fallback={(err, reset) => (
      <div>
        <p>Something went wrong: {String(err)}</p>
        <button onClick={reset}>Retry</button>
      </div>
    )}>
      <Suspense fallback={<div>Loading…</div>}>
        <UserProfile />
      </Suspense>
    </ErrorBoundary>
  )
}
```

The `reset` callback passed to `ErrorBoundary`'s fallback re-renders the boundary's children from scratch. You can combine it with `refetch` for a full retry:

```tsx
function UserProfile() {
  const [user, { refetch }] = createResource(userId, fetchUser)

  return (
    <ErrorBoundary fallback={(err, reset) => (
      <button onClick={() => { refetch(); reset() }}>Retry</button>
    )}>
      <div>{user()?.name}</div>
    </ErrorBoundary>
  )
}
```

### Reading `data.error` directly (no throw)

If you want to handle errors inline rather than propagate to a boundary, read `data.error` directly:

```tsx
function UserProfile() {
  const [user] = createResource(userId, fetchUser)

  return (
    <div>
      {user.error && <p class="error">{String(user.error)}</p>}
      {user() && <p>{user()!.name}</p>}
    </div>
  )
}
```

> Reading `data.error` does **not** throw to `<ErrorBoundary>`. Reading `data()` while errored **does** throw. Choose based on whether you want centralized or local error handling.

---

## Multiple resources under one `<Suspense>`

```tsx
import { createResource, Suspense } from "solid-js"

function Dashboard() {
  const [user] = createResource(() => fetchUser(1))
  const [posts] = createResource(() => fetchPosts(1))
  const [stats] = createResource(() => fetchStats())

  // All three fetch in parallel; Suspense above waits for all of them
  return (
    <div>
      <h1>{user()?.name}</h1>
      <ul>
        {posts()?.map(p => <li>{p.title}</li>)}
      </ul>
      <p>Total posts: {stats()?.postCount}</p>
    </div>
  )
}

// Wrap at the route/page level
function DashboardPage() {
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <Dashboard />
    </Suspense>
  )
}
```

Resources fetch in **parallel** automatically — they are not sequential. Each `createResource` starts its own async fetch.

---

## `<SuspenseList>` — ordered reveal

When multiple sibling `<Suspense>` boundaries should reveal in a specific order (to avoid layout jumps), `<SuspenseList>` coordinates them.

```tsx
import { SuspenseList, Suspense } from "solid-js"

// experimental — check Solid release notes for stability
<SuspenseList revealOrder="forwards" tail="collapsed">
  <Suspense fallback={<Spinner />}><Hero /></Suspense>
  <Suspense fallback={<Spinner />}><Content /></Suspense>
  <Suspense fallback={<Spinner />}><Sidebar /></Suspense>
</SuspenseList>
```

`revealOrder` options:
- `"forwards"` — reveal in document order regardless of which resolves first
- `"backwards"` — reveal in reverse order
- `"together"` — reveal all at once when all are ready

`tail` controls how many spinners show: `"collapsed"` shows only the last, `"hidden"` shows none.

> `<SuspenseList>` is marked experimental in Solid v1.9.x. It is useful but be prepared for possible API changes.

---

## `useTransition()` / `startTransition()` — no-flash navigation

Transitions let you start async work (e.g., navigating to a new route, loading new data) while keeping the **current UI visible** — no fallback flash. The user sees the old screen while the new data loads, then the new screen appears fully rendered.

### `useTransition()`

```ts
import { useTransition } from "solid-js"

const [pending, start] = useTransition()
//      ▲               ▲
//   Accessor<boolean>  (fn: () => void) => Promise<void>
```

`pending()` is `true` while async work inside the transition is still resolving.

```tsx
import { createSignal, useTransition } from "solid-js"

function NavButton() {
  const [page, setPage] = createSignal("home")
  const [pending, start] = useTransition()

  function navigate(to: string) {
    start(() => setPage(to))
    // The resource that reads page() starts fetching
    // but the current UI stays visible until done
    // pending() is true during this time
  }

  return (
    <div>
      <nav style={{ opacity: pending() ? 0.6 : 1 }}>
        <button onClick={() => navigate("home")}>Home</button>
        <button onClick={() => navigate("profile")}>Profile</button>
      </nav>
      {/* The page component reads from page() signal */}
    </div>
  )
}
```

### `startTransition(fn)`

A module-level function — use when you don't need the `pending` flag:

```ts
import { startTransition } from "solid-js"

startTransition(() => {
  setCurrentTab("settings")
})
```

### How transitions work with `<Suspense>`

Without a transition: changing a signal that drives a resource immediately puts the resource into `"pending"`, which triggers `<Suspense>` fallback.

With a transition: Solid defers committing the signal change until all resources triggered by it have resolved. The existing rendered tree stays visible (and interactive). The fallback is never shown for that `<Suspense>`.

> `@solidjs/router` uses transitions internally for route navigation — that is why navigating between routes never shows a Suspense fallback by default.

---

## `createDeferred` — low-priority derived value

`createDeferred` creates a derived accessor that defers updates until the browser is idle (via `requestIdleCallback`). Use it when you need a derived value but its consumers are non-urgent (e.g., a secondary panel that can lag behind).

```ts
import { createSignal, createDeferred } from "solid-js"

const [filter, setFilter] = createSignal("")

// filteredList updates urgently
const filteredList = () => bigList.filter(item => item.name.includes(filter()))

// deferredList only updates when the browser is idle
const deferredList = createDeferred(filteredList, { timeoutMs: 200 })
```

---

## `createSelector` — O(1) active-item tracking

`createSelector` efficiently tracks which item in a list is "selected" without re-rendering the whole list when selection changes. It creates a boolean accessor per item that only updates when that specific item enters or leaves the selected state.

```tsx
import { createSignal, createSelector, For } from "solid-js"

const [selectedId, setSelectedId] = createSignal<number | null>(null)

// isSelected(id) returns true only when selectedId() === id
// Updates are O(1): only the previously selected and newly selected rows re-run
const isSelected = createSelector(selectedId)

function List({ items }: { items: { id: number; name: string }[] }) {
  return (
    <For each={items}>
      {(item) => (
        <li
          classList={{ active: isSelected(item.id) }}
          onClick={() => setSelectedId(item.id)}
        >
          {item.name}
        </li>
      )}
    </For>
  )
}
```

Without `createSelector`, every row would re-check `selectedId() === item.id` on every selection change — O(n) updates. `createSelector` makes it O(2) (only the old and new selected rows update).

---

## `initialValue` option — avoid the `undefined` flash

When you know a resource will produce a value and you want to avoid the `unresolved → pending` states, provide `initialValue`:

```ts
const [user, { refetch }] = createResource(
  userId,
  fetchUser,
  { initialValue: { id: 0, name: "Loading…", email: "" } }
)
// user() is immediately the initialValue; no undefined state
// TypeScript also knows user() is T (not T | undefined)
```

---

## `onHydrated` option — SSR hydration callback

```ts
const [data] = createResource(source, fetcher, {
  onHydrated: (sourceValue, { value }) => {
    // Called after hydration when the resource's value is populated from SSR
    // value is the hydrated value (may be undefined if not serialized)
  }
})
```

Relevant for SSR/SSG; not commonly needed in the reference app (Tauri app, no SSR).

---

## Worked example — profile page with loading, error, and refresh

```tsx
import { createSignal, createResource, Suspense, ErrorBoundary, Show } from "solid-js"

type User = { id: number; name: string; email: string; bio: string }

async function fetchUser(id: number): Promise<User> {
  const res = await fetch(`/api/users/${id}`)
  if (!res.ok) throw new Error(`Failed to fetch user: ${res.status}`)
  return res.json()
}

function UserProfile() {
  const [userId] = createSignal(42)
  const [user, { refetch }] = createResource(userId, fetchUser)

  return (
    <ErrorBoundary
      fallback={(err, reset) => (
        <div class="error">
          <p>{String(err)}</p>
          <button onClick={() => { refetch(); reset() }}>Try again</button>
        </div>
      )}
    >
      <Suspense fallback={<div class="skeleton">Loading profile…</div>}>
        {/* user() throws to Suspense while pending, throws to ErrorBoundary if errored */}
        <div class="profile">
          <Show when={user.loading}>
            <span class="spinner" aria-label="Refreshing" />
          </Show>
          <h1>{user()?.name}</h1>
          <p>{user()?.email}</p>
          <p>{user()?.bio}</p>
          <button onClick={() => refetch()}>Refresh</button>
        </div>
      </Suspense>
    </ErrorBoundary>
  )
}
```

Key points in this example:
- `<ErrorBoundary>` wraps `<Suspense>` — catches thrown errors from errored resources.
- `<Suspense>` shows the skeleton until the first load completes.
- `user.loading` drives an inline spinner for subsequent refreshes (no fallback flash).
- `refetch()` re-runs the fetcher; `reset()` clears the error boundary.

---

## Positioning — when to use what

```
createResource    →  One-off local async: config file, file picker, one-time derive
createQuery       →  Server state: user data, lists, any data shared/cached across views
```

`createQuery` (from `@tanstack/solid-query`) adds:
- Automatic caching by key — the same data is not re-fetched when navigating back
- Deduplication — two components asking for the same key share one request
- Background refetch on window focus, stale-while-revalidate
- Mutation + invalidation workflows

Both integrate with `<Suspense>` identically. The reactive options-function idiom in Solid Query mirrors the source-signal pattern in `createResource` — see [11-solid-query.md](11-solid-query.md).

> **When you're unsure:** if the data lives on a server and might be read by more than one component, use `createQuery`. If the data is truly local and the lifetime of the async result matches the component, `createResource` is simpler and has no extra dependency.

---

## See also

- [04-control-flow.md](04-control-flow.md) — `<Show>`, `<For>`, `<ErrorBoundary>`, `<Suspense>` in context
- [06-stores.md](06-stores.md) — `reconcile` to merge fetched data into a store
- [11-solid-query.md](11-solid-query.md) — `createQuery`/`createMutation`, the caching layer the reference app uses for server state
- [15-pitfalls.md](15-pitfalls.md) — common async mistakes (reading resources outside tracking scope, forgetting ErrorBoundary)
