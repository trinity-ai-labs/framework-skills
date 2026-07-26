# Architecture — structuring a Solid app (the the reference app way)

> **When you reach for this:** before you add the second feature. The other chapters teach the parts — signals, stores, control flow, Solid Query, the router. This one teaches how to *assemble* them into an app that stays easy to change. It's grounded in how the reference app's desktop app is actually built; the structure here is observed, not invented.

The thesis is the same one the **`effect-v3`** skill's architecture chapter opens with (Ousterhout, Brooks, Beck): **bad code is code that is hard to change.** Solid's fine-grained reactivity gives you a specific kind of leverage — updates are surgical and a component runs once — but that leverage evaporates if you blur the two things every app must keep straight: **where data lives** and **where the boundaries are**. This chapter is about getting those right.

---

## Contents

- [The big boundary: Solid app vs Effect sidecar](#the-big-boundary-solid-app-vs-effect-sidecar)
- [Two kinds of state, two tools](#two-kinds-of-state-two-tools)
- [The data layer: a centralized Solid Query module](#the-data-layer-a-centralized-solid-query-module)
- [Provider composition at the root](#provider-composition-at-the-root)
- [File and route layout](#file-and-route-layout)
- [Component conventions](#component-conventions)
- [Where reactivity lives](#where-reactivity-lives)
- [Putting it together: the data flow](#putting-it-together-the-data-flow)
- [Habits that keep the app changeable](#habits-that-keep-the-app-changeable)
- [See also](#see-also)


## The big boundary: Solid app vs Effect sidecar

the reference app is a Tauri desktop app. It has two halves, and the cleanest single fact about its architecture is the line between them:

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│   SOLID APP (the webview)     │   api   │   EFFECT SIDECAR (backend)   │
│                               │ ───────▶│                              │
│  • UI + components            │  HTTP   │  • business logic            │
│  • reactive state             │  / IPC  │  • persistence (SQLite)      │
│  • navigation (router)        │ ◀─────  │  • git, agents, sync, SSE    │
│  • Solid Query cache          │  JSON   │  • Effect services & layers  │
└──────────────────────────────┘         └──────────────────────────────┘
        signals / stores                       Effect<A, E, R>
        @tanstack/solid-query                  Context / Layer / Scope
```

- **The Solid frontend owns the UI**: rendering, reactive state, navigation, and the *cache of server data*. It never reaches past the `api` client. It is `solid-js` + `@solidjs/router` + `@tanstack/solid-query` (+ Kobalte for primitives).
- **The Effect sidecar owns the backend**: business rules, the database, git operations, agent orchestration, realtime fan-out. It's a separate process built the Effect way; for that code, use the **`effect-v3`** skill.
- **They talk over an `api` client** — HTTP/IPC to the local sidecar, JSON in and out. The frontend's `api` (the reference app: `@/api`, plus raw `fetch('/api/...')` for some mutations) is the *only* seam between the halves.

> **The rule:** `app = Solid + Solid Query + signals/stores; sidecar = Effect services/layers.` **Solid code never imports `effect`.** The frontend doesn't know `Effect<A, E, R>` exists — it knows it can call `api.projects.get(id)` and get a `Promise<Project>` back. The error/dependency/concurrency machinery lives on the other side of the wire. the reference app does **not** use `@effect-atom` in the app; server data flows through Solid Query, never an Effect-on-the-client bridge.

This boundary is what lets each half be a deep module to the other. The frontend treats the sidecar as "a service that returns JSON"; the sidecar treats the frontend as "a client that makes requests." Neither leaks into the other's internals.

---

## Two kinds of state, two tools

The single most consequential design decision in a Solid app is *where each piece of state lives*. Get this wrong and you'll hand-roll caching in effects, or stuff ephemeral UI flags into the query cache, and the app gets brittle. The rule is binary:

| State is… | Lives in | Examples |
| --- | --- | --- |
| **Server state** — owned by the backend, fetched, cached, can go stale | **Solid Query** (`createQuery`) | project list, settings, a release, presence, metrics |
| **Local / UI state** — owned by the client, ephemeral, never round-trips | **signals + stores + context** | "is this dialog open", form draft values, active tab, theme, the UI-active project |

**Server state → Solid Query.** It owns the cache, request dedup, staleness, background refetch, and invalidation. You describe *what* to fetch and under *which key*; the cache owns *when*. Don't reinvent this with `createResource` + a signal, and never with `createEffect` + `setSignal`.

**Local/UI state → signals and stores.** A single value is a `createSignal`; deep/structured local state is a `createStore` (per-property tracking, `produce`/`reconcile` updates — see [Stores](06-stores.md)); state shared across a subtree goes in a `createContext` provider.

```tsx
// ❌ Server data stuffed into a signal, synced by an effect — you've hand-rolled
//    a worse cache: no dedup, no invalidation, races on every refetch.
const [projects, setProjects] = createSignal<Project[]>([])
createEffect(async () => setProjects(await api.projects.list()))   // don't
```

```tsx
// ✅ Server data is a query; the cache owns fetching, staleness, invalidation.
const projectsQuery = useProjects()        // wraps createQuery
//    UI state is a signal; it never round-trips to the server.
const [editing, setEditing] = createSignal(false)
```

The inverse mistake is just as real: don't put ephemeral UI flags (dialog-open, hover, the in-progress form draft) into the query cache. They're not server state; they have no key, no staleness, no invalidation story. They're signals.

> **A telling the reference app case.** The *UI-active project* is a **signal** in the auth provider (`activeProjectId`), deliberately distinct from the server's view of it (`useProjects().data?.activeProjectId`, which lags a switch by one network round-trip). Flipping the signal is synchronous; the server-side activation is a separate POST. That's the rule in miniature: the snappy client-owned pointer is a signal; the authoritative persisted value is server state behind a query.

---

## The data layer: a centralized Solid Query module

Server state being Solid Query doesn't mean scattering `createQuery` calls with inline keys across components. the reference app centralizes the entire data layer in one module (`src/lib/query/`, imported as `@/query`). It has four parts, and the payoff is that keys and freshness policy live in *one* place instead of drifting across hundreds of call sites.

### 1. A typed key factory

Every query key comes from a factory, never a hand-typed array. the reference app's keys fall into three **tiers** by what they scope to:

```ts
// @/query/hooks/keys.ts — keys are branded so the cache refuses bare arrays.
type GlobalKey<Tail>  = [...Tail]                          // account-agnostic
type AccountKey<Tail> = [accountId: string, ...Tail]       // per-account
type ScopedKey<Tail>  = [accountId: string, scope: string, ...Tail]  // per-scope (personal/team)

export const scopedKeys = {
  projects: (scope: ScopeArg) => defineScopedKey(scope, "projects"),
  project:  (scope: ScopeArg, id: string) => defineScopedKey(scope, "project", id),
  settings: (scope: ScopeArg) => defineScopedKey(scope, "settings"),
  // …one entry per query family, each a pure function of its args.
} as const

export function toScopeArg(scope: ActiveScope): ScopeArg { /* accountId + scopeKey */ }
export function defineGlobalKey<const Tail>(...tail: Tail): GlobalKey<Tail> { /* … */ }
```

Why centralize keys:

- **One slot per logical query.** A hook reads `scopedKeys.projects(scope)`; a mutation invalidates `scopedKeys.projects(scope)`; a test seeds `scopedKeys.projects(scope)`. Same factory, same slot — they can't drift apart.
- **Scope safety by construction.** Every per-scope key is prefixed `(accountId, scopeKey, …)`. Two scopes (personal vs a team) get *different* keys for the same query, so their caches can't collide. Switching scope doesn't need `queryClient.clear()` — the new scope's slots are simply different keys.
- **Branded keys + a typed cache wrapper.** The key types carry a phantom brand, and `@tanstack/query-core`/`solid-query` are augmented so `QueryClient`'s methods *require* a branded key. A bare `['projects']` won't compile. The cache-mutating call sites go through a thin wrapper (`appCache.invalidate/setData/getData`) that only accepts branded keys — closing the cross-scope-leak class at the type layer, not by discipline.

### 2. Option tiers (freshness presets)

Freshness policy is a small set of named presets, not a per-hook guess. Spread the tier into the query options:

```ts
// @/query/tiers.ts
export const QUERY_TIERS = {
  static:         { staleTime: Infinity, gcTime: Infinity },               // invalidation-driven only
  doorbellBacked: { staleTime: 30*60_000, gcTime: 30*60_000, refetchOnWindowFocus: true }, // realtime-pushed
  stable:         { staleTime: 5*60_000,  gcTime: 30*60_000 },             // settings, sponsorship
  semiStable:     { staleTime: 60_000,    gcTime: 10*60_000 },             // edited occasionally
  live:           { staleTime: 10_000,    gcTime: 5*60_000 },              // edited together, polled
  realtime:       { staleTime: 2_000,     gcTime: 2*60_000 },              // timer-driven UI
} as const
```

A `gc-time.ts` helper layers on top (active-scope vs background-scope `gcTime`, so cache held for teams you're *not* looking at is bounded). Why presets matter: every hook author picks a *tier name* that documents intent ("this is doorbell-backed", "this is settings, stale-by-minutes is fine") instead of sprinkling magic numbers. Tuning freshness across the app is editing one file.

### 3. A typed cache wrapper

`@/query/typed-cache.ts` wraps `queryClient.invalidateQueries/setQueryData/getQueryData` so cache writes require a branded key and read/write through one audited surface. Mutations and realtime handlers call `appCache.invalidate(qc, key)`, never the raw client.

### 4. Per-feature hooks

Components don't call `createQuery` directly. Each query family is a `useX()` hook that wraps `createQuery(() => ({...}))` and bakes in the key, the tier, and the scope-gating. Components just call the hook.

```ts
// @/query/hooks/projects.ts — the real shape.
export function useProjects() {
  const auth = useAuthContext()
  return createQuery(() => {
    const scope = auth.activeScope()
    return {
      // options go in a FUNCTION so they re-track when scope changes (see Solid Query ch.)
      queryKey: scope
        ? scopedKeys.projects(toScopeArg(scope))
        : defineGlobalKey("projects", "logged-out"),
      queryFn: () => api.projects.list(),
      enabled: scope !== null,           // don't fetch until we have a scope
      ...QUERY_TIERS.doorbellBacked,     // freshness preset
      gcTime: getScopedGcTime(scope, scope),
    }
  })
}
```

Two Solid-Query idioms are load-bearing here and worth internalizing (full detail in [Solid Query](11-solid-query.md)):

- **Options-as-a-function.** `createQuery(() => ({...}))` — the callback re-runs when the signals it reads change (here `auth.activeScope()`), so the query *re-keys and refetches* on scope switch automatically. Pass an object literal instead and the query freezes at mount.
- **`enabled` gating.** The query is inert until the scope exists, so it never fires a logged-out request.

A mutation lives in the same feature hook and invalidates the families it affects on success:

```ts
const saveMutation = createMutation(() => ({
  mutationFn: (fields) => api.projects.update(id(), fields),
  onSuccess: () => {
    const scopeArg = toScopeArg(auth.activeScope()!)
    void appCache.invalidate(queryClient, scopedKeys.project(scopeArg, id()))   // re-read this project
    void appCache.invalidate(queryClient, scopedKeys.projects(scopeArg))        // and the list
    void appCache.invalidate(queryClient, scopedKeys.activity(scopeArg))        // and the activity feed
  },
}))
```

> **The data layer is itself a deep module.** Its public surface is `useX()` hooks + the key factories; everything else (tiers, gc-time math, the branded-key plumbing, the typed-cache wrapper) is hidden behind that. A component knows `useProjects()` and `scopedKeys.projects`; it knows nothing about how freshness is tuned. Just like an Effect service, the boundary is the interface.

---

## Provider composition at the root

Cross-cutting concerns — theme, the query client, toasts, auth, realtime, background tasks, notifications, presence, updates — are **providers** stacked at the app root. The stack is **ordered**, and the order is not cosmetic: later providers depend on earlier ones.

```tsx
// app.tsx — Router root={Shell}; the stack lives in Shell.
function Shell(props) {
  return (
    <ThemeProvider …>                  {/* 1. theme: leaf, depends on nothing  */}
      <QueryClientProvider client={queryClient}>  {/* 2. the cache — everything below queries through it */}
        <ToastProvider>                {/* 3. toasts: used by the providers below to surface errors */}
          <AuthProvider>               {/* 4. auth: establishes the active scope/account */}
            <ActiveProjectBootstrap>   {/*    seeds the UI-active project from the projects query */}
              <SSEProvider>            {/* 5. realtime: needs auth (subscribes per scope) */}
                <TaskProvider>         {/* 6. background tasks: need auth + realtime */}
                  <NotificationProvider>
                    <PresenceProvider> {/*    presence: needs auth (who am I) + realtime (broadcast) */}
                      <UpdateProvider>
                        {/* app chrome + routed page */}
                        {props.children}
                      </UpdateProvider>
                    </PresenceProvider>
                  </NotificationProvider>
                </TaskProvider>
              </SSEProvider>
            </ActiveProjectBootstrap>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export function App() {
  return (
    <Router root={Shell}>
      <Route path="/" component={DashboardPage} />
      <Route path="/projects/:id/settings" component={EditProjectPage} />
      {/* …one Route per page; nested routes under layout components */}
    </Router>
  )
}
```

**Why order matters.** `QueryClientProvider` must be above anything that queries. `AuthProvider` must be above anything that needs the active scope — which is most of the stack: `SSEProvider` subscribes to realtime *for the current scope*, `PresenceProvider` broadcasts *as the current user*, every `useX()` hook keys on `auth.activeScope()`. The stack is a dependency order, top to bottom, the same way an Effect layer graph wires services bottom-up. Reorder it and a lower provider reads context that isn't there yet.

**The guarded `useX()` pattern.** Every provider exposes a context plus a hook that throws if used outside it — so a missing provider is a loud error at the call site, not a silent `undefined`:

```tsx
// @/components/providers/auth.tsx
const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuthContext(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuthContext must be used within AuthProvider")
  return ctx
}
```

The context value is built from **signals and memos** (`activeScope` is a `createMemo` with a custom `equals` so it keeps referential identity across unrelated state ticks). Consumers call `auth.activeScope()` — an accessor — so they stay reactive to scope changes. See [Context](08-context.md) for the typed-provider pattern in full.

> **The `Router root={Shell}` move.** The provider stack lives in the router's `root` so it wraps *every* route once and survives navigation — the cache, auth, and realtime connections aren't torn down and rebuilt as the user moves between pages. Full-window routes (the reference app drops the sidebar/chrome for the IDE-style `/code` view) are handled with a `Show` *inside* `Shell`, not by escaping the provider stack.

---

## File and route layout

the reference app is **file-per-page** under `src/app/<route>/page.tsx`, mirroring a filesystem-routing convention even though routes are declared explicitly in `app.tsx`. The structure:

```
src/
  app.tsx                       # Router + provider stack (Shell) + <Route> table
  app/
    page.tsx                    # "/" — the dashboard
    projects/
      page.tsx                  # "/projects"
      [id]/
        settings/
          page.tsx              # "/projects/:id/settings"
          components/           # co-located presentational components for this page
            project-details-card.tsx
            project-details-card.test.tsx
          hooks/
            use-edit-project.ts # co-located feature hook (query + form signals + mutation)
    knowledge/
      layout.tsx                # a nested LAYOUT route — wraps its children
      page.tsx                  # "/knowledge" (index)
      [book]/[section]/[chapter]/page.tsx
  components/
    providers/                  # the root provider stack (theme, auth, sse, task, …)
    layout/                     # sidebar, title bar — app chrome
    ...                         # shared, cross-feature components
  lib/
    query/                      # THE DATA LAYER (imported as @/query)
      client.ts                 #   the QueryClient singleton
      tiers.ts  gc-time.ts  typed-cache.ts
      hooks/                    #   per-feature useX() hooks + keys.ts
    api/                        # the api client — the sidecar seam
    auth/  git/  ...            # other lib domains
```

The conventions:

- **A page is a route component**, `app/<route>/page.tsx`. Dynamic segments are `[id]` directories. The `<Route>` table in `app.tsx` maps paths to these.
- **Nested layouts are layout routes.** `knowledge/layout.tsx` is a parent `<Route>` with child routes inside it; the layout renders shared chrome and `<Outlet>`-style children. See [Router](10-router.md) for nested-route mechanics.
- **Co-locate by feature.** A page's `components/` and `hooks/` sit next to its `page.tsx`. The settings page owns `use-edit-project.ts` (its query + form signals + save mutation) and a `components/` folder of presentational cards. Tests sit beside the file they test (`*.test.tsx`).
- **Shared components and the data layer are central**, under `components/` and `lib/query/`. Anything used across features lifts up; anything used by one page stays co-located.

This is the Solid analogue of the Effect skill's "feature-oriented, then role inside it" layout: a feature is a deep module (`page.tsx` + its `components/` + its `hooks/`), and only the genuinely shared pieces (providers, the query layer, the api client) live at the top.

---

## Component conventions

Within a component, a handful of rules keep the fine-grained reactivity intact (each links to its full chapter):

- **Small, presentational components.** Push data-fetching into a feature hook; let the component take props and render. The `project-details-card` takes `{ name, onSaveField, … }` and nothing else — which is exactly why it [tests](13-testing.md) without any providers.
- **Derive, don't sync.** Reach for `createMemo` (or a plain `() => …` accessor) before `createEffect`+`setSignal`. An effect that writes a signal to mirror another is almost always a memo. → [Reactivity](02-reactivity.md)
- **Props down, events up.** Parents pass data via props (accessors stay reactive) and receive changes via callbacks. Don't have a child write its parent's signal directly.
- **Never destructure props or store fields.** `props.value` is reactive; `const { value } = props` freezes it at mount. Use `splitProps`/`mergeProps`. → [Components & props](03-components-and-props.md)
- **Control-flow components over JS.** `<Show>`/`<For>`/`<Index>`/`<Switch>` — a JSX `if`/`.map()` runs once and never updates. Pick `<For>` (keyed by identity) vs `<Index>` (keyed by position) deliberately. → [Control flow](04-control-flow.md)

---

## Where reactivity lives

A clean Solid app keeps each reactive primitive in its lane:

| Primitive | Owns | Don't use it for |
| --- | --- | --- |
| `createSignal` | a single piece of local UI state | server data, derived values |
| `createStore` | deep/structured local state, per-property tracking | a single value (use a signal) |
| `createMemo` | derived values — anything computable from other reactive sources | side effects |
| `createEffect` | **true** side effects only: DOM mutation, subscriptions, logging, syncing to a non-reactive system | deriving a value (that's a memo) |
| **Solid Query** | server-cache reactivity — fetch/dedup/stale/refetch/invalidate | ephemeral UI flags |
| `createContext` | state shared across a subtree | global mutable singletons reached by import |

The most common smell is an effect doing a memo's job. The the reference app edge cases where an effect *is* right: seeding form signals from a freshly-fetched query (`createEffect(() => { const p = projectQuery.data; if (p) setName(p.name) })` — syncing the query cache *into* editable local state is a genuine side effect), and syncing reactive state out to a non-reactive system (stamping ambient request headers when scope/project changes). Both are "react to a change by touching something outside the reactive graph" — that's what effects are for. Everything else is a memo.

---

## Putting it together: the data flow

A user action travels a short, well-defined path — and the *only* re-rendering at the end is a fine-grained DOM update, never a component re-run:

```
 user clicks "Save"
        │
        ▼
 component event handler  ──────────────┐
        │                               │
   (local edit?)                  (server write?)
        │                               │
        ▼                               ▼
  setSignal / setStore           createMutation.mutate()
        │                               │  ── api call ──▶  Effect sidecar
        │                               ◀── JSON ───────  (validates, persists,
        │                               │                   emits SSE doorbell)
        │                          onSuccess:
        │                          appCache.invalidate(qc, scopedKeys.x(scope))
        │                               │
        │                               ▼
        │                       Solid Query marks the slot stale →
        │                       the useX() hooks subscribed to that key refetch
        │                               │
        └───────────────┬───────────────┘
                        ▼
        the specific reactive reads that depend on the changed
        signal / query data re-run — updating individual text nodes
        and attributes directly. No VDOM diff, no component re-render.
```

Two paths, one shape: a **local** change flips a signal/store; a **server** change goes out through a mutation and comes back as a cache invalidation that refetches the affected queries. Either way the reactive graph propagates the change to exactly the DOM that depends on it. Realtime push (SSE doorbells from the sidecar) feeds the same invalidation machinery, so a teammate's change updates your UI through the identical "invalidate → refetch → fine-grained update" flow.

---

## Habits that keep the app changeable

- **Decide where state lives first.** Server or local? That answer picks the tool (Solid Query vs signal/store) and prevents the two evergreen mistakes — caching in effects, and UI flags in the query cache.
- **Route every key and freshness choice through the data layer.** New query family ⇒ new factory in `keys.ts` + a `useX()` hook with a `QUERY_TIERS` preset. Never an inline key, never a magic `staleTime`.
- **Keep components presentational; put data in hooks.** A component that takes props and renders is trivially testable and trivially reusable. One that fetches and reaches into five providers is neither.
- **Respect the provider order.** It's a dependency graph. Auth before anything scoped; the query client above anything that queries.
- **Never let `effect` cross the wire.** The frontend speaks `api` and `Promise`; the sidecar speaks `Effect`. If you're tempted to import `effect` in a component, the boundary is in the wrong place.

---

## See also

- [Reactivity](02-reactivity.md) — signals/memos/effects; derive-don't-sync
- [Components & props](03-components-and-props.md) — never destructure props, `splitProps`/`mergeProps`
- [Stores](06-stores.md) — deep local state, `produce`/`reconcile`
- [Context](08-context.md) — typed providers and the guarded `useX()` pattern
- [Router](10-router.md) — `Router root={…}`, nested layout routes, params
- [Solid Query](11-solid-query.md) — the options-function idiom, keys, invalidation, the QueryClient
- [Testing](13-testing.md) — why these boundaries make the app testable; seeding the cache
- The **`effect-v3`** skill — the other side of the wire: services, layers, the sidecar's architecture
