# @solidjs/router — routing, params, layouts, and data

`@solidjs/router` is the official, universal router for SolidJS. It handles client navigation, nested layouts, reactive route params and search params, and an optional data layer (`query`, `createAsync`, `action`). the reference app uses it as a **client-side SPA router** inside a Tauri window — for navigation, params, and layout outlets — while server data goes through `@tanstack/solid-query` (see the note in the Data APIs section).

> **Version.** This chapter targets **`@solidjs/router` v0.16.x** (current stable is `0.16.2`), paired with `solid-js` 1.9. The data API was renamed across earlier versions: `cache` → **`query`**, the route `data` / `routeData` prop → **`load`** → **`preload`**, and `useRouteData` was removed. Everything below uses the **current names**; the old ones still exist as `@deprecated` aliases (`cache`, the `load` prop, `RouteLoadFunc`) but you should not write them.
>
> 0.15 → 0.16 is **additive** — nothing in this chapter changed. The only public-API movement: `useNavigate()`'s first overload now accepts `string | number`, `RouteDefinition.component` widened to the new `RouteSectionComponent` type (so a component that ignores `children` type-checks), and `RouterContext` is re-exported. A `1.0.0-next` line exists but tracks Solid 2.0 and is not stable.

```bash
pnpm add @solidjs/router
```

All imports in this chapter come from `"@solidjs/router"`.

---

## Contents

- [Mental model](#mental-model)
- [Setup — `<Router>` and the `root` layout](#setup-router-and-the-root-layout)
- [`<Route>` and path syntax](#route-and-path-syntax)
- [Nested routes & layout outlets](#nested-routes-layout-outlets)
- [Config-based routes](#config-based-routes)
- [Navigation primitives](#navigation-primitives)
- [Reactive params & location](#reactive-params-location)
- [Data APIs](#data-apis)
- [API quick reference](#api-quick-reference)
- [the reference app recap](#the-reference-app-recap)


## Mental model

A router is a reactive function from the current **location** to a tree of **matched routes**. Each match contributes a component; nested matches render *inside* their parent via an **outlet** (the parent receives matched children as `props.children`). Because the location is a signal, everything downstream — `useParams`, `useSearchParams`, `useLocation`, `useMatch` — is **reactive**: read them in a tracking scope and they update on navigation without remounting.

```
location signal ──► branch matching ──► RouteMatch[] ──► nested component tree
   │                                                          │
   useLocation / useParams / useSearchParams ◄── reactive ────┘
```

There is no SSR in the reference app (it's a Tauri SPA), so the SSR-flavoured concerns — `deferStream`, single-flight mutations, `StaticRouter` — are mostly irrelevant; they're noted for completeness.

---

## Setup — `<Router>` and the `root` layout

```tsx
import { Router, Route } from "@solidjs/router";
import { render } from "solid-js/web";

render(() => <App />, document.getElementById("root")!);
```

The `<Router>` is the top of the tree. Routes are declared as JSX `<Route>` children. The `root` prop names a component that **wraps every route** — it receives the matched route tree as `props.children` and is the place for app chrome (providers, sidebar, title bar) that must persist across navigations *without remounting*.

```tsx
import type { JSX } from "solid-js";
import { Router, Route, useLocation } from "@solidjs/router";

// The root layout: rendered ONCE, wraps every route. props.children is the outlet.
function Shell(props: { children?: JSX.Element }) {
  const location = useLocation();
  return (
    <div class="app">
      <Sidebar current={location.pathname} />
      <main>{props.children}</main>
    </div>
  );
}

export function App() {
  return (
    <Router root={Shell}>
      <Route path="/" component={DashboardPage} />
      <Route path="/projects/:id/settings" component={EditProjectPage} />
    </Router>
  );
}
```

This is exactly the reference app's shape (`src/app.tsx`): a `Shell` root that mounts every provider (`ThemeProvider`, `QueryClientProvider`, `ToastProvider`, …) plus the sidebar/title-bar, then renders `props.children`. Because `root` lives above the route switch, those providers and the query cache survive navigation.

### `<Router>` props

| Prop | Type | Meaning |
|---|---|---|
| `root` | `Component<RouteSectionProps>` | Layout wrapping every route; receives `props.children` (the outlet). |
| `base` | `string` | Base path prefix for all routes (e.g. app served under `/app`). |
| `rootPreload` | `RoutePreloadFunc` | Preload that runs for the root layout on every navigation. |
| `preload` | `boolean` | Master switch for link/route preloading (default `true`). |
| `actionBase` | `string` | URL base used to register `action()` endpoints. |
| `explicitLinks` | `boolean` | If `true`, only `<A>` triggers client nav; bare `<a>` does full reloads. |
| `singleFlight` | `boolean` | SSR-only: combine mutation + revalidation into one round-trip. |
| `children` | `JSX.Element \| RouteDefinition[]` | `<Route>` JSX **or** a config object array (see below). |

> **`root` vs nested layout routes.** `root` is the *single* outermost wrapper. For section-specific chrome (a docs sidebar that only some pages get), use a **nested `<Route>` with a `component`** instead — covered under Nested layouts.

### Router variants

The default `<Router>` uses the browser History API (`pushState`/`popState`) — correct for a Tauri SPA, and what the reference app uses. Alternatives share the same `<Route>` children:

| Router | Import | Use when |
|---|---|---|
| `Router` | `@solidjs/router` | Default; History API URLs (`/projects/42`). The the reference app choice. |
| `HashRouter` | `@solidjs/router` | URLs in the hash (`/#/projects/42`); for static hosts with no server rewrite. |
| `MemoryRouter` | `@solidjs/router` | In-memory history, no URL bar; tests and embedded/non-browser shells. |
| `StaticRouter` | `@solidjs/router` | SSR: render one fixed `url` per request. Not used client-side. |

```tsx
import { HashRouter, MemoryRouter } from "@solidjs/router";

<HashRouter root={Shell}>{/* routes */}</HashRouter>
<MemoryRouter root={Shell}>{/* routes — handy in unit tests */}</MemoryRouter>
```

---

## `<Route>` and path syntax

```tsx
import { Route } from "@solidjs/router";
```

| Prop | Type | Meaning |
|---|---|---|
| `path` | `string \| string[]` | Path pattern(s) this route matches. |
| `component` | `Component<RouteSectionProps>` | Component to render when matched. |
| `children` | `JSX.Element` | Nested `<Route>`s — this route becomes a layout. |
| `matchFilters` | `MatchFilters` | Per-segment validators (regex / string list / predicate). |
| `preload` | `RoutePreloadFunc` | Runs before the component renders (and on link hover/focus). |
| `info` | `Record<string, any>` | Arbitrary metadata, readable from `useCurrentMatches()`. |

### Path patterns

| Pattern | Example | Matches | `params` |
|---|---|---|---|
| Static | `/projects` | `/projects` | `{}` |
| Dynamic | `/projects/:id` | `/projects/42` | `{ id: "42" }` |
| Multi-dynamic | `/:book/:chapter` | `/solid/router` | `{ book: "solid", chapter: "router" }` |
| Optional | `/users/:id?` | `/users` **and** `/users/42` | `{}` or `{ id: "42" }` |
| Splat (catch-all) | `/files/*rest` | `/files/a/b/c.txt` | `{ rest: "a/b/c.txt" }` |
| Bare splat | `*404` | anything unmatched | `{ "404": "..." }` |
| Multiple paths | `path={["/login", "/signin"]}` | either | `{}` |

```tsx
<Route path="/projects" component={ProjectsPage} />
<Route path="/projects/:id/settings" component={EditProjectPage} />
<Route path="/users/:id?" component={UserPage} />        {/* optional segment */}
<Route path="/files/*rest" component={FileBrowser} />     {/* splat → params.rest */}
<Route path="*404" component={NotFound} />                {/* catch-all fallback  */}
<Route path={["/login", "/signin"]} component={Login} />  {/* multiple paths      */}
```

> **Routes are scored, not ordered.** The router ranks matches by specificity (static beats dynamic beats splat), so a `*404` catch-all can sit anywhere — it only wins when nothing more specific matches. You don't have to order routes carefully the way you would with a naive switch.

### `matchFilters` — validate dynamic segments

`matchFilters` rejects a match when a segment fails validation, letting a less-specific route (or `*404`) win instead. A filter is a regex, a string allow-list, or a predicate.

```tsx
import { Route } from "@solidjs/router";
import type { SegmentValidators } from "@solidjs/router";

// /post/123 matches; /post/abc falls through to the next route
<Route
  path="/post/:id"
  component={Post}
  matchFilters={{ id: /^\d+$/ }}
/>

<Route
  path="/lang/:code"
  component={Localized}
  matchFilters={{ code: ["en", "es", "fr"] }} // allow-list
/>
```

---

## Nested routes & layout outlets

A `<Route>` that has child `<Route>`s becomes a **layout**: its `component` renders, and the matched child is handed to it as `props.children` — the **outlet**. Child `path`s are appended to the parent's. This is how the reference app builds its Knowledge and Gotchas sections.

```tsx
import { Show, type JSX } from "solid-js";

// The layout component — renders the section chrome + the outlet.
function KnowledgeLayout(props: { children?: JSX.Element }) {
  const manifest = useKnowledgeManifest(() => "knowledge");
  return (
    <div class="docs">
      <PageHeader title="Knowledge Base" />
      <Show when={manifest.data?.books.length} fallback={<>{props.children}</>}>
        <KnowledgeShell manifest={manifest.data!.books}>
          {props.children}  {/* ◄── the matched child route renders here */}
        </KnowledgeShell>
      </Show>
    </div>
  );
}

// Mirrors a real src/app.tsx. Child paths are RELATIVE to /knowledge.
<Route path="/knowledge" component={KnowledgeLayout}>
  <Route path="/" component={KnowledgeIndexPage} />
  <Route path="/:book" component={KnowledgeBookPage} />
  <Route path="/:book/:section/:chapter" component={KnowledgeChapterPage} />
  <Route path="/:book/:section/:chapter/:page" component={KnowledgePagePage} />
</Route>
```

Navigating `/knowledge/solid/core/signals` mounts `KnowledgeLayout` once, then swaps which leaf page renders in its outlet. The layout (and its data fetch) is **not** remounted between sibling pages — only the leaf changes. Layouts nest arbitrarily deep; each parent passes the next match through its `props.children`.

> **Layout `component` ≠ leaf `component`.** A layout *must* render `props.children` somewhere, or its child routes never appear. A leaf route ignores `props.children`.

---

## Config-based routes

Instead of JSX, you can pass an array of `RouteDefinition` objects as the `<Router>`'s children. Same shape, useful when routes are generated programmatically (e.g. from a manifest).

```tsx
import { Router, type RouteDefinition } from "@solidjs/router";

const routes: RouteDefinition[] = [
  { path: "/", component: DashboardPage },
  {
    path: "/knowledge",
    component: KnowledgeLayout,
    children: [
      { path: "/", component: KnowledgeIndexPage },
      { path: "/:book", component: KnowledgeBookPage },
    ],
  },
];

export const App = () => <Router root={Shell}>{routes}</Router>;
```

> Each object accepts the same fields as `<Route>`: `path`, `component`, `children`, `matchFilters`, `preload`, `info`. (`useRoutes` from earlier versions is gone — passing the array as children replaces it.)

> **Code-splitting by route** lives in [Performance § Lazy loading and code splitting](12-performance.md) — wrap the route component in Solid's `lazy(() => import(…))` and put a `<Suspense>` above the outlet. It composes with `preload` (warm the data) and `usePreloadRoute` (warm the chunk).

---

## Navigation primitives

### `<A>` vs bare `<a>`

`<A>` is the client-side link: it intercepts the click, navigates without a full page load, resolves relative `href`s against the current route, and adds active classes when the URL matches.

```tsx
import { A } from "@solidjs/router";
```

| Prop | Type | Default | Meaning |
|---|---|---|---|
| `href` | `string` | — | Target path (relative resolves against current route). |
| `activeClass` | `string` | `"active"` | Class applied when the link matches the location. |
| `inactiveClass` | `string` | `"inactive"` | Class applied when it does not. |
| `end` | `boolean` | `false` | If `true`, match the path **exactly** (no prefix match). |
| `replace` | `boolean` | `false` | Use `replaceState` instead of `pushState`. |
| `noScroll` | `boolean` | `false` | Don't scroll to top after navigating. |
| `state` | `unknown` | — | History state, readable via `useLocation().state`. |

```tsx
{/* `end` so "/" isn't marked active on every page (it's a prefix of all). */}
<A href="/" end activeClass="text-primary">Home</A>
<A href="/projects" activeClass="text-primary">Projects</A>
```

```tsx
// ❌ A bare <a> does a full document reload — in a Tauri SPA this reboots the whole app.
<a href="/projects">Projects</a>

// ✅ <A> navigates in-app, preserving providers and query cache.
<A href="/projects">Projects</A>
```

### `useNavigate` — imperative navigation

```tsx
import { useNavigate } from "@solidjs/router";

function SaveButton() {
  const navigate = useNavigate();
  const onDone = () => navigate("/projects", { replace: true });
  // navigate(-1) goes back; second arg is Partial<NavigateOptions>:
  //   { replace, resolve, scroll, state }
  return <button onClick={onDone}>Save</button>;
}
```

This is the reference app's redirect-after-resolve pattern (e.g. the Knowledge chapter index navigates to the chapter's first page with `{ replace: true }`).

### `<Navigate>` — declarative redirect

Renders nothing and redirects on mount. `href` may be a function for computed targets.

```tsx
import { Navigate } from "@solidjs/router";

<Route path="/onboard" component={() => <Navigate href="/projects/new" />} />
<Navigate href={({ location }) => `/login?from=${location.pathname}`} />
```

---

## Reactive params & location

### `useParams` — dynamic segments (reactive)

```tsx
import { useParams } from "@solidjs/router";

const params = useParams<{ id: string }>();
// params is a reactive store. Reading params.id in a tracking scope re-runs on nav.
```

Params are **always strings** (URL text). They're a *store*, so `params.id` is a reactive read — not a snapshot.

```tsx
// ❌ Destructuring snapshots the value — it won't update when you navigate
//    /projects/1 → /projects/2 without remounting.
const { id } = useParams();
fetchProject(id); // stale forever

// ✅ Keep the reactive read; wrap it in a thunk so consumers re-track.
const params = useParams<{ id: string }>();
const project = useProjectQuery(() => params.id); // re-fetches on id change
```

> **The canonical pattern: pass `() => params.id` into your query.** Solid Query (and the router's own `createAsync`) take *accessor* inputs so the source key is reactive. Passing the raw `params.id` value captures a snapshot; passing `() => params.id` lets the query re-key when the route changes. This is exactly how the reference app wires param pages to `@tanstack/solid-query`.

### `useSearchParams` — query string (reactive get + setter)

Returns a `[params, setParams]` tuple. The getter store is reactive; the setter does a *merge*-style navigation (only the keys you pass change; pass `null`/`undefined` to delete).

```tsx
import { useSearchParams } from "@solidjs/router";

const [searchParams, setSearchParams] = useSearchParams<{ tab: string; q: string }>();

searchParams.tab;                       // reactive read of ?tab=...
setSearchParams({ tab: "files" });      // → ?tab=files (merges with existing params)
setSearchParams({ q: undefined });      // removes ?q
setSearchParams({ tab: "x" }, { replace: true }); // 2nd arg: Partial<NavigateOptions>
```

### `useLocation` — the current location (reactive)

```tsx
import { useLocation } from "@solidjs/router";

const location = useLocation();
location.pathname; // "/projects/42/settings"
location.search;   // "?tab=files"
location.hash;     // "#section"
location.query;    // parsed search params object
location.state;    // history state passed via navigate/<A state>
```

the reference app's `Shell` reads `location.pathname` to decide which routes render full-window (dropping the sidebar). Because it's reactive, the decision re-evaluates on every navigation.

### `useMatch` — does the location match a pattern?

```tsx
import { useMatch } from "@solidjs/router";

const match = useMatch(() => "/projects/*"); // accessor in, Accessor<PathMatch | undefined> out
const onProjects = () => Boolean(match());
```

### `useCurrentMatches` — the full matched chain

```tsx
import { useCurrentMatches } from "@solidjs/router";

const matches = useCurrentMatches();
// () => RouteMatch[] — each has .path, .params, .route (incl. the route's `info`).
// Build breadcrumbs by mapping over matches() and reading route.info.
```

### `useIsRouting` — transition in flight

`true` while an async navigation (a `preload`/transition) is pending — drive a top-of-page loading bar.

```tsx
import { useIsRouting } from "@solidjs/router";

const isRouting = useIsRouting();
<Show when={isRouting()}><TopProgressBar /></Show>
```

### `useBeforeLeave` — guard navigation

Fires before leaving the current route; call `e.preventDefault()` to block, then `e.retry(true)` to proceed (e.g. after a confirm dialog).

```tsx
import { useBeforeLeave, type BeforeLeaveEventArgs } from "@solidjs/router";

useBeforeLeave((e: BeforeLeaveEventArgs) => {
  if (!formIsDirty()) return;
  e.preventDefault();
  if (window.confirm("Discard unsaved changes?")) e.retry(true);
});
```

### `usePreloadRoute` — warm a route manually

```tsx
import { usePreloadRoute } from "@solidjs/router";

const preload = usePreloadRoute();
// e.g. on hover of a custom control: run the target route's preload early.
preload("/projects/42/settings", { preloadData: true });
```

---

## Data APIs

> **the reference app does not use these for server data.** the reference app fetches all backend data through **`@tanstack/solid-query`** (`QueryClientProvider` in `Shell`, `useQuery` wrappers in `src/query/*`), and uses the router purely for navigation, params, and layouts. The data layer below is documented for completeness and for projects that adopt the router-native flow — but in the reference app, reach for Solid Query, not `query`/`createAsync`.

The router's data layer has three pieces that compose: **`query`** (a deduped/cached async function), **`createAsync`** (a reactive accessor that reads a query under Suspense), and **`action`** (a mutation with submission tracking).

### `query` — cached, deduped async function (formerly `cache`)

```tsx
import { query } from "@solidjs/router";
```

`query(fn, name)` wraps an async function so identical calls within a tick are deduped and results are cached by serialized arguments under `name`. It returns a callable with `.key` and `.keyFor(...args)` helpers.

```tsx
import { query } from "@solidjs/router";

// name MUST be unique across the app — it's the cache namespace.
const getProject = query(async (id: string) => {
  const res = await fetch(`/api/projects/${id}`);
  return res.json() as Promise<Project>;
}, "project");

getProject.key;            // "project"
getProject.keyFor("42");   // "project[...]" — the per-args cache key
```

| Member | Signature | Use |
|---|---|---|
| call | `query(...args) => Promise<T>` | Invoke; deduped + cached. |
| `.key` | `string` | The base cache name. |
| `.keyFor(...args)` | `string` | The exact cache key for these args. |
| `query.get/set/delete/clear` | static | Manual cache poke (rare). |

### `createAsync` — reactive accessor over an async source

```tsx
import { createAsync } from "@solidjs/router";
```

`createAsync(fn, options?)` runs `fn` reactively (re-running when its tracked dependencies change) and returns an **accessor** that integrates with Suspense — `undefined` until the promise settles, unless you pass `initialValue`. It's a thin wrapper over `createResource`.

```tsx
import { createAsync } from "@solidjs/router";
import { useParams } from "@solidjs/router";

function ProjectPage() {
  const params = useParams<{ id: string }>();
  // Re-runs whenever params.id changes; getProject dedupes against the cache.
  const project = createAsync(() => getProject(params.id));
  return (
    <Suspense fallback={<Spinner />}>
      <h1>{project()?.name}</h1>
    </Suspense>
  );
}
```

`options`: `{ name?, initialValue?, deferStream? }`. With `initialValue` the accessor is non-nullable from the start. The returned accessor also exposes `.latest` (the last settled value during a pending refetch).

### `createAsyncStore` — same, but a fine-grained store

Identical to `createAsync` but the result is wrapped in a store and diffed with `reconcile`, so consumers only re-render the fields that actually changed — ideal for large objects/lists. Extra option: `reconcile?: ReconcileOptions`.

```tsx
import { createAsyncStore } from "@solidjs/router";

const todos = createAsyncStore(() => getTodos(), { initialValue: [] });
```

### The `preload` prop — fetch before render

A route's `preload` runs *before* the component renders **and** when a link to it is hovered/focused, priming the `query` cache so `createAsync` resolves instantly. It receives `{ params, location, intent }`.

```tsx
import { Route, type RoutePreloadFuncArgs } from "@solidjs/router";

// Note: this is `preload`, NOT the old `load`/`data` prop.
const preloadProject = ({ params }: RoutePreloadFuncArgs) => {
  void getProject(params.id); // warm the cache; don't await
};

<Route path="/projects/:id" component={ProjectPage} preload={preloadProject} />
```

> `intent` is `"initial" | "native" | "navigate" | "preload"` — e.g. skip expensive work on the `"preload"` (hover) intent and only do it on real navigation.

### `action` + `useAction` + `useSubmission` — mutations

```tsx
import { action, useAction, useSubmission, revalidate } from "@solidjs/router";
```

`action(fn, name?)` wraps an async mutation. You can either submit it via a `<form action={...} method="post">` (it doubles as a serializable form action) or call it imperatively with `useAction`. `useSubmission` exposes the live state of the latest submission (`pending`, `result`, `error`, `input`).

```tsx
import { action, useAction, useSubmission, revalidate } from "@solidjs/router";

const renameProject = action(async (id: string, name: string) => {
  await fetch(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
  await revalidate(getProject.keyFor(id)); // invalidate the cached query → createAsync refetches
}, "renameProject");

function RenameForm(props: { id: string }) {
  const rename = useAction(renameProject);
  const submission = useSubmission(renameProject);
  return (
    <form onSubmit={(e) => { e.preventDefault(); rename(props.id, name()); }}>
      <input value={name()} onInput={(e) => setName(e.currentTarget.value)} />
      <button disabled={submission.pending}>
        {submission.pending ? "Saving…" : "Rename"}
      </button>
      <Show when={submission.error}>{(err) => <p class="error">{String(err())}</p>}</Show>
    </form>
  );
}
```

| API | Returns | Use when |
|---|---|---|
| `action(fn, name?)` | `Action` | Declare a mutation (also a form-action value). |
| `useAction(action)` | `(...args) => Promise` | Call the action imperatively from code. |
| `useSubmission(action, filter?)` | `Submission \| Stub` | Track the **latest** matching submission. |
| `useSubmissions(action, filter?)` | `Submission[] & { pending }` | Track **all** in-flight submissions (optimistic lists). |
| `revalidate(key?, force?)` | `Promise<void>` | Invalidate query cache key(s) → trigger refetch. |
| `redirect(url, init?)` | `Response` | Return from an action to redirect (SSR/throwable). |
| `reload(init?)` / `json(data, init?)` | `Response` | Action response helpers (revalidate / typed body). |

`Submission` shape: `{ input, result?, error, pending, url, clear(), retry() }`.

---

## API quick reference

| Hook / API | Returns | Use when |
|---|---|---|
| `useParams<T>()` | reactive `Params` store | Read dynamic `:segments` / splats; pass `() => params.x` to queries. |
| `useSearchParams<T>()` | `[store, setter]` | Read/merge-update the query string reactively. |
| `useLocation<S>()` | reactive `Location` | Read `pathname`/`search`/`hash`/`query`/`state`. |
| `useNavigate()` | `(to, opts?) => void` | Imperative navigation; `navigate(-1)` for back. |
| `useMatch(() => pattern)` | `Accessor<PathMatch \| undefined>` | Test whether the location matches a pattern. |
| `useCurrentMatches()` | `() => RouteMatch[]` | Build breadcrumbs / read each match's `route.info`. |
| `useIsRouting()` | `() => boolean` | Show a global transition / loading indicator. |
| `useBeforeLeave(fn)` | `void` | Guard navigation (unsaved-changes confirm). |
| `usePreloadRoute()` | `(url, opts?) => void` | Manually warm a route's preload/data. |
| `query(fn, name)` | `CachedFunction` | Dedupe + cache an async fn (router data layer). |
| `createAsync(fn, opts?)` | `AccessorWithLatest<T>` | Reactive, Suspense-aware read of an async source. |
| `createAsyncStore(fn, opts?)` | `AccessorWithLatest<T>` | Same, store-backed with `reconcile` diffing. |
| `action(fn, name?)` | `Action` | Declare a mutation / form action. |
| `useAction(action)` | `(...args) => Promise` | Invoke an action imperatively. |
| `useSubmission(s)` / `useSubmissions(s)` | `Submission` / `Submission[]` | Track mutation state (single / all). |
| `revalidate(key?, force?)` | `Promise<void>` | Invalidate `query` cache → refetch. |
| `<A href activeClass end>` | element | Client-side link with active styling. |
| `<Navigate href>` | `null` | Declarative redirect on mount. |
| `<Route path component preload>` | element | Declare a route / nested layout. |
| `<Router root base preload>` | element | Mount the router; `root` wraps every route. |

---

## the reference app recap

- **Default `<Router root={Shell}>`** — `Shell` mounts every provider + the sidebar/title-bar and renders `props.children`; it's the persistent app frame.
- **JSX `<Route>`s** with static paths, `:id` dynamic segments, and **nested layout routes** (`/knowledge`, `/gotchas`) whose layout `component` renders `props.children` as the outlet.
- **Reactive params** read via `useParams()` and passed as `() => params.id` into `@tanstack/solid-query` hooks — the router supplies the *key*, Solid Query supplies the *data*.
- **`useLocation`** drives layout decisions (full-window vs chrome); **`useNavigate`** does redirect-after-resolve with `{ replace: true }`.
- The router's `query`/`createAsync`/`action` data layer is **unused** in the reference app — Solid Query owns server state.
