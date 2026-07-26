# Solid Query — server-state for SolidJS

Reach for **`@tanstack/solid-query`** (Solid Query) whenever a value lives on a server and you want it cached, deduplicated, kept fresh in the background, and shared across every component that asks for the same key. It is the SolidJS adapter of TanStack Query — the same battle-tested cache engine that powers React Query — wired into Solid's fine-grained reactivity instead of React's render loop.

> **the reference app runs its entire server-data layer on Solid Query.** Every read from the website data plane (projects, releases, threads, activity, metrics, settings…) is a `createQuery`; every write is a `createMutation`; the cache is the single source of truth that SSE/doorbell invalidations and optimistic patches both flow through. If you touch data in the reference app, you are touching Solid Query.

This chapter targets **`@tanstack/solid-query` v5** (current stable is `5.101.4`) on `solid-js` 1.9.

> **`createQuery` or `useQuery`?** The package exports **both** — `useQuery`, `useMutation`, `useInfiniteQuery` and friends are the primary names shared with the rest of TanStack Query, and `createQuery`/`createMutation`/`createInfiniteQuery` are Solid-flavoured aliases for the same functions. Neither is deprecated. This chapter uses the `create*` spelling because it matches Solid's own primitive naming; if you read TanStack's docs site you will see `use*` for the identical API. `useQueryClient` has no `create*` alias.
>
> A **v6** line exists in alpha/beta, but it is the adapter for **Solid 2.0** — it is not a v5 successor for Solid 1.9 apps and should not be adopted here.

---

## Contents

- [Mental model](#mental-model)
- [Setup — `QueryClient` + `<QueryClientProvider>`](#setup-queryclient-queryclientprovider)
- [THE KEY IDIOM — options are a **function**, not an object](#the-key-idiom-options-are-a-function-not-an-object)
- [`createQuery(() => options)`](#createquery-options)
- [Query keys](#query-keys)
- [`createMutation(() => options)`](#createmutation-options)
- [`useQueryClient()` + the imperative cache API](#usequeryclient-the-imperative-cache-api)
- [`createInfiniteQuery` (pagination)](#createinfinitequery-pagination)
- [Reactive `enabled` & dependent queries](#reactive-enabled-dependent-queries)
- [`staleTime` vs `gcTime`, and option tiers](#staletime-vs-gctime-and-option-tiers)
- [Testing (brief)](#testing-brief)
- [When to use Solid Query vs `createResource` vs a plain signal](#when-to-use-solid-query-vs-createresource-vs-a-plain-signal)
- [Cheat-sheet](#cheat-sheet)


## Mental model

A **query** is a declarative subscription to an async source, addressed by a **query key**. The `QueryClient` holds a cache keyed by those keys. When a component mounts a query:

- If the cache has **fresh** data for the key (`now < dataUpdatedAt + staleTime`), it's served instantly with no fetch.
- If the cache has **stale** data, it's served instantly *and* a background refetch runs (stale-while-revalidate).
- If the cache is empty, the query fetches and the result is `isPending`.

Multiple components mounting the same key share **one** cache entry and **one** in-flight request (deduplication). When the last observer of a key unmounts, the entry is kept warm for `gcTime` before being garbage-collected.

```
createQuery(() => options) ─┐
createQuery(() => options) ─┼─► QueryClient cache ──► one entry per queryKey
createQuery(() => options) ─┘        (dedup, staleTime, gcTime, structural sharing)
                                            ▲
createMutation(...).mutate() ───► queryClient.invalidateQueries / setQueryData
```

### Solid Query vs `createResource`

`createResource` (covered in the async chapter) is Solid's **lower-level primitive**: a signal-driven async value with `loading`/`error`/`latest`. It has no shared cache, no key-based dedup across components, no background revalidation, no stale-time policy, no invalidation API. You wire all of that yourself.

Solid Query is the **cache layer on top of that idea**. Reach for it the moment two components need the same server value, the moment you want "refetch when this changes," or the moment you want a mutation to invalidate a read.

| Need | Reach for |
|---|---|
| One-off async value local to a component, no sharing | `createResource` |
| Same server value read in several places, deduped | **Solid Query** |
| Background refetch / stale-while-revalidate / focus refetch | **Solid Query** |
| Mutation that should refresh related reads | **Solid Query** (`invalidateQueries`) |
| Optimistic updates with rollback | **Solid Query** (`onMutate` + `setQueryData`) |
| Pagination / infinite scroll with a shared cache | **Solid Query** (`createInfiniteQuery`) |
| Pure client state (open/closed, form draft, counter) | a plain `createSignal` / `createStore` — **not** a query |

---

## Setup — `QueryClient` + `<QueryClientProvider>`

Create one `QueryClient`, configure its defaults, and wrap the app once at the root.

```tsx
// query/client.ts
import { QueryClient } from '@tanstack/solid-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false, // opt in per-query instead
      staleTime: 60_000,           // 60s "nothing special" baseline
      gcTime: 300_000,             // keep unobserved entries 5min before GC
      retry: 1,                    // one retry on failure
    },
  },
});
```

> **the reference app's client is a module-level singleton.** Inside the Tauri webview there is no SSR/hydration boundary, so the `QueryClient` is created once at module scope and exported directly. Components that need to seed or invalidate the cache *outside* a hook (e.g. the SSE provider) import `queryClient` directly; components inside the tree use `useQueryClient()`.

Wrap the app root:

```tsx
// app.tsx
import { QueryClientProvider } from '@tanstack/solid-query';
import { queryClient } from '@/query/client';

export function App(props: { children: JSX.Element }) {
  return (
    <QueryClientProvider client={queryClient}>
      {/* AuthProvider, SSEProvider, router, … */}
      {props.children}
    </QueryClientProvider>
  );
}
```

Every `createQuery` / `createMutation` / `useQueryClient()` below this provider reads from this one client.

### `QueryClientConfig` defaults you'll actually set

`defaultOptions.queries` accepts every per-query option as a default. The ones worth setting globally:

| Default | Meaning |
|---|---|
| `staleTime` | How long fetched data counts as fresh (no background refetch). Default `0` — *everything* refetches on mount. Set a baseline. |
| `gcTime` | How long an entry with **no observers** survives before garbage collection. Default `300_000` (5 min). |
| `retry` | Retry count on a failed `queryFn`. Default `3`; the reference app uses `1`. |
| `refetchOnWindowFocus` | Refetch stale queries when the tab regains focus. Default `true`; the reference app defaults it **off** and opts in per-query. |
| `refetchOnReconnect` | Refetch stale queries when the network reconnects. Default `true`. |

---

## THE KEY IDIOM — options are a **function**, not an object

This is the single most important thing in this chapter, and the one place Solid Query departs hard from React Query.

In React Query you pass a plain options **object**: React re-runs the component on every render, so a fresh object is produced each time and the library diffs it. Solid components **run once** — there is no re-render to regenerate that object. So Solid Query takes the options as a **function that returns the options object**, and re-invokes that function inside a reactive computation. Any signal you read *inside* the function (`id()`, `activeScope()`, …) is tracked; when it changes, the function re-runs, the options change, and the query reacts — refetching, re-keying, or toggling `enabled` automatically.

```tsx
// ❌ WRONG — a plain object. Read once, never reactive. `id()` is sampled
//    a single time at creation; changing the signal never refetches.
const q = createQuery({
  queryKey: ['project', id()],
  queryFn: () => api.projects.get(id()),
});
```

```tsx
// ✅ RIGHT — a function returning options. Re-runs reactively whenever any
//    tracked signal it reads (here `id()`) changes, driving refetch/re-key.
const q = createQuery(() => ({
  queryKey: ['project', id()],
  queryFn: () => api.projects.get(id()),
}));
```

> **Say it again because it's the whole ballgame:** the options function is your reactive boundary. Read signals *inside* it. A signal read inside the function makes the query depend on that signal; a signal read outside (and captured into a closure) does not. This is why `queryKey`, `enabled`, `staleTime` — anything computed from a signal — must be computed *in the function body*.

the reference app's real read hook (`use-edit-project.ts`) is exactly this shape:

```tsx
import { createQuery, useQueryClient } from '@tanstack/solid-query';
import { api } from '@/api';
import { useAuthContext } from '@/components/providers/auth';
import { defineGlobalKey, scopedKeys, toScopeArg } from '@/query/hooks/keys';
import { getScopedGcTime } from '@/query/gc-time';
import { QUERY_TIERS } from '@/query/tiers';

export function useEditProject(id: () => string) {
  const auth = useAuthContext();

  const projectQuery = createQuery(() => {
    const scope = auth.activeScope();          // tracked
    return {
      queryKey: scope
        ? scopedKeys.project(toScopeArg(scope), id()) // tracked: id()
        : defineGlobalKey('edit-project', 'logged-out'),
      queryFn: () => api.projects.get(id()),
      enabled: scope !== null && !!id(),        // tracked
      ...QUERY_TIERS.semiStable,                // staleTime + gcTime preset
      gcTime: getScopedGcTime(scope, scope),
    };
  });

  return { project: () => projectQuery.data ?? null };
}
```

When `id()` changes the key changes → Solid Query treats it as a different cache entry and fetches it. When `activeScope()` flips to `null` (logged out) `enabled` goes false and the query parks. No `createEffect`, no manual refetch call.

---

## `createQuery(() => options)`

### Options

All read off the object returned by your options function. The function re-runs reactively, so any of these can be computed from signals.

| Option | Type | What it does |
|---|---|---|
| `queryKey` | `readonly unknown[]` | The cache address. Serializable array; deterministic. **Required.** |
| `queryFn` | `(ctx) => Promise<T>` | Fetches the data. Receives a context (below). **Required** unless a default is registered. |
| `enabled` | `boolean` | When `false`, the query won't fetch automatically and sits in `pending`/`idle`. Drives dependent queries. |
| `staleTime` | `number \| Infinity` | ms data stays fresh before a background refetch is eligible. `Infinity` = never stale. |
| `gcTime` | `number \| Infinity` | ms an **unobserved** entry survives before GC. |
| `retry` | `number \| boolean \| (failureCount, error) => boolean` | Retry policy for a throwing `queryFn`. |
| `retryDelay` | `number \| (attempt, error) => number` | Backoff between retries. Default exponential. |
| `refetchOnWindowFocus` | `boolean \| 'always'` | Refetch on tab focus. `'always'` ignores `staleTime`. |
| `refetchOnReconnect` | `boolean \| 'always'` | Refetch on network reconnect. |
| `refetchInterval` | `number \| false \| (query) => number` | Poll on a timer. |
| `placeholderData` | `T \| (prev, prevQuery) => T` | Synchronous stand-in shown while fetching; **not** written to cache. Pass `keepPreviousData` (the identity fn) to hold the last page during re-keys. |
| `select` | `(data) => U` | Transform/narrow the data the component sees. Re-runs when data changes; doesn't touch the cache. |
| `initialData` | `T \| () => T` | Seed the cache synchronously as if it were fetched. Counts as real data (subject to `staleTime`). |
| `meta` | `Record<string, unknown>` | Arbitrary metadata passed to `queryFn`'s context and error handlers. |

> **`placeholderData` vs `initialData`:** `initialData` is written to the cache and is treated as a genuine fetched value (so `staleTime` applies and it persists). `placeholderData` is a render-only fallback — never cached, replaced the instant a real fetch resolves, and the query still reports `isPlaceholderData: true` while it's showing.

### The `queryFn` context

`queryFn` receives one argument with:

| Field | Use |
|---|---|
| `queryKey` | The resolved key array — derive fetch params from it instead of closing over signals. |
| `signal` | An `AbortSignal` wired to query cancellation — forward it to `fetch` for automatic abort on unmount/re-key. |
| `meta` | The `meta` you set in options. |

```tsx
const q = createQuery(() => ({
  queryKey: ['project', id()] as const,
  queryFn: async ({ queryKey, signal }) => {
    const [, projectId] = queryKey;
    const res = await fetch(`/api/projects/${projectId}`, { signal });
    if (!res.ok) throw new Error('Failed to fetch project');
    return res.json() as Promise<Project>;
  },
}));
```

### The returned object — reactive accessors on a proxy

`createQuery` returns a **reactive store proxy**. Every field is a live accessor: reading `query.data` inside a tracking scope (JSX, a `createMemo`, a `createEffect`) subscribes to *just that field*.

| Field | Meaning |
|---|---|
| `data` | The cached data, or `undefined` while pending (or the `select` output / placeholder). |
| `error` | The thrown error, or `null`. |
| `status` | `'pending' \| 'error' \| 'success'` — the *data* state. |
| `fetchStatus` | `'fetching' \| 'paused' \| 'idle'` — the *request* state, orthogonal to `status`. |
| `isPending` | `status === 'pending'` — no data yet. (The v5 name; replaces v4 `isLoading`.) |
| `isLoading` | `isPending && isFetching` — first load in flight. |
| `isFetching` | A request is in flight (initial **or** background refetch). |
| `isSuccess` | `status === 'success'` — data is present. |
| `isError` | `status === 'error'`. |
| `isStale` | Data is past its `staleTime`. |
| `isRefetching` | A background refetch (not the first load) is running. |
| `isPlaceholderData` | The shown `data` is placeholder, not real cache data. |
| `dataUpdatedAt` | Epoch ms of the last successful fetch. |
| `refetch()` | Imperatively refetch this query; returns a promise of the result. |

> **Never destructure the result.** `const { data } = createQuery(...)` snapshots the accessor's *current value* and severs reactivity — `data` will never update. Keep the proxy and read fields where you need them, **in tracking scope**:

```tsx
// ❌ destructured — frozen at first value, never updates
const { data, isPending } = createQuery(() => ({ /* … */ }));

// ✅ read fields off the proxy, inside JSX (a tracking scope)
const q = createQuery(() => ({ /* … */ }));
return (
  <Switch>
    <Match when={q.isPending}>Loading…</Match>
    <Match when={q.isError}>Error: {q.error?.message}</Match>
    <Match when={q.isSuccess}>{q.data!.name}</Match>
  </Switch>
);
```

> **`status` (data) vs `fetchStatus` (request) are orthogonal on purpose.** A query can be `status: 'success'` *and* `fetchStatus: 'fetching'` at the same time — that's the background refetch of stale data. `isPending` tells you "do I have data to show?"; `isFetching` tells you "is a request running?". A disabled query that has never fetched is `status: 'pending'`, `fetchStatus: 'idle'`.

---

## Query keys

A query key is a **serializable array** that uniquely names a cache entry. Solid Query hashes it deterministically (object key order doesn't matter), so the same logical key always lands in the same slot.

### Hierarchical / scoped keys

Keys are **prefix-matched** for invalidation. Structure them coarse-to-fine so a short prefix can invalidate a whole family:

```ts
['project', id]                          // one project
['project', id, 'targets']               // its targets — child of the above
['project', id, 'members']               // its members
```

Invalidating `['project', id]` matches *every* key that starts with that prefix — the project and all its children — in one call. This is the backbone of cache invalidation, so design keys with the prefixes you'll want to invalidate.

### Structural sharing

When a refetch returns data that is **deeply equal** to what's cached, Solid Query keeps the *previous object references* (structural sharing). Components reading unchanged sub-objects don't see a new reference, so derived memos and effects don't needlessly re-run. This is why returning fresh-but-equal JSON from a poll is cheap.

### Key factories — the typed registry pattern

Inline `queryKey: ['project', id]` literals rot: a typo silently creates a phantom cache slot, and invalidators drift out of sync with readers. The fix is a **typed key-factory module** — one place that mints every key. the reference app centralizes all of them in `query/hooks/keys.ts`, branded into three tiers:

```ts
// query/hooks/keys.ts (abridged)
type Brand<T, B extends string> = T & { readonly __brand: B };

export type GlobalKey<Tail extends readonly unknown[]> =
  Brand<readonly [...Tail], 'GlobalKey'>;
export type ScopedKey<Tail extends readonly unknown[]> =
  Brand<readonly [accountId: string, scope: string, ...Tail], 'ScopedKey'>;

export type ScopeArg = {
  readonly accountId: string;
  readonly scopeKey: 'personal' | `team:${string}`;
};

export function defineGlobalKey<const Tail extends readonly unknown[]>(
  ...tail: Tail
): GlobalKey<Tail> {
  return tail as unknown as GlobalKey<Tail>;
}

function defineScopedKey<const Tail extends readonly unknown[]>(
  scope: ScopeArg,
  ...tail: Tail
): ScopedKey<Tail> {
  return [scope.accountId, scope.scopeKey, ...tail] as unknown as ScopedKey<Tail>;
}

export const scopedKeys = {
  projects: (scope: ScopeArg) => defineScopedKey(scope, 'projects'),
  project: (scope: ScopeArg, id: string) => defineScopedKey(scope, 'project', id),
  projectTargets: (scope: ScopeArg, id: string) =>
    defineScopedKey(scope, 'project', id, 'targets'),
  activity: (scope: ScopeArg, filters?: ActivityQueryFilters) =>
    defineScopedKey(scope, 'activity', filters ?? {}),
  // … one entry per cache slot in the app
} as const;
```

Why bother:

- **Single source of truth.** Reader and invalidator call the *same* factory — they can never disagree on key shape.
- **Scope-prefixing for free.** Every scoped key starts with `[accountId, scopeKey, …]`, so personal vs. team data lands in distinct slots and switching scope can't leak another scope's cache.
- **Type-level enforcement.** the reference app augments `@tanstack/query-core` and `@tanstack/solid-query`'s `Register` interface to pin `queryKey` to the branded union, so `QueryClient`'s methods *refuse a bare array at compile time*:

  ```ts
  declare module '@tanstack/solid-query' {
    interface Register { queryKey: AnyAppKey; }
  }
  ```

  A typed-cache wrapper (`appCache.invalidate/getData/setData`) takes only branded keys, so cache mutations can't be written against a stray inline array.

> **Takeaway for your own app:** even without the branding, a `keys.ts` module of small factory functions is the difference between an invalidation that works and one that silently misses. Build it on day one.

---

## `createMutation(() => options)`

Writes go through `createMutation`. Same function-options idiom. You don't call the `mutationFn` directly — you call `.mutate(vars)` (fire-and-forget) or `.mutateAsync(vars)` (returns a promise).

```tsx
import { createMutation, useQueryClient } from '@tanstack/solid-query';

export function useInviteMember() {
  const queryClient = useQueryClient();
  const auth = useAuthContext();

  return createMutation(() => ({
    mutationFn: (vars: { teamId: string; handleOrEmail: string }) =>
      api.teams.inviteMember(vars.teamId, vars.handleOrEmail),
    onSuccess: (_data, variables) => {
      const accountId = auth.activeAccountId() ?? 'unknown';
      void queryClient.invalidateQueries({
        queryKey: accountKeys.teamMembers(accountId, variables.teamId),
      });
    },
  }));
}

// in a component:
const invite = useInviteMember();
<button disabled={invite.isPending} onClick={() => invite.mutate({ teamId, handleOrEmail })}>
  Invite
</button>
```

### Mutation options & result

| Option | Fires |
|---|---|
| `mutationFn(vars)` | The write itself. |
| `onMutate(vars)` | **Before** the request — return value becomes the `context` passed to later callbacks. Where optimistic patches + cancellation go. |
| `onSuccess(data, vars, context)` | After success — invalidate / reconcile here. |
| `onError(err, vars, context)` | After failure — roll back here using `context`. |
| `onSettled(data, err, vars, context)` | After success *or* failure — final reconcile. |

| Result field | Meaning |
|---|---|
| `mutate(vars)` | Trigger; returns `void`. Errors land in `onError` / `mutation.error`. |
| `mutateAsync(vars)` | Trigger; returns a `Promise<data>` (rejects on failure). |
| `isPending` | The mutation is in flight. |
| `isSuccess` / `isError` | Terminal states. |
| `data` / `error` | Last result / error. |
| `reset()` | Clear back to idle. |

### Optimistic updates — `onMutate` + `setQueryData` + rollback

The full pattern: cancel in-flight reads, snapshot the current cache, patch it optimistically, return the snapshot as context, roll back in `onError`, reconcile in `onSettled`. This is the reference app's `useUpdateProject`, verbatim in shape:

```tsx
export function useUpdateProject() {
  const queryClient = useQueryClient();
  const auth = useAuthContext();

  return createMutation(() => ({
    mutationFn: (params: { id: string; data: UpdateProjectData }) =>
      api.projects.update(params.id, params.data),

    onMutate: async (variables) => {
      const scope = auth.activeScope();
      if (!scope) throw new Error('not authenticated');
      const scopeArg = toScopeArg(scope);
      const projectKey = scopedKeys.project(scopeArg, variables.id);

      // 1. Cancel outgoing refetches so they can't clobber the optimistic write.
      await queryClient.cancelQueries({ queryKey: projectKey });

      // 2. Snapshot the current value for rollback.
      const prevProject = queryClient.getQueryData<ProjectWithStats>(projectKey);

      // 3. Optimistically patch the cache.
      if (prevProject) {
        queryClient.setQueryData<ProjectWithStats>(projectKey, {
          ...prevProject,
          ...variables.data,
        });
      }

      // 4. Hand the snapshot (and the scope we pinned) to later callbacks.
      return { scope, prevProject };
    },

    onError: (_err, variables, context) => {
      // 5. Roll back to the snapshot.
      if (context?.prevProject) {
        const scopeArg = toScopeArg(context.scope);
        queryClient.setQueryData(scopedKeys.project(scopeArg, variables.id), context.prevProject);
      }
    },

    onSettled: (_data, _err, variables, context) => {
      // 6. Reconcile with the server's canonical row (server-computed fields,
      //    normalization the optimistic patch can't predict).
      const scope = context?.scope ?? auth.activeScope();
      if (!scope) return;
      const scopeArg = toScopeArg(scope);
      void queryClient.invalidateQueries({ queryKey: scopedKeys.project(scopeArg, variables.id) });
    },
  }));
}
```

> **Pin the scope in `onMutate`, not in `onError`/`onSettled`.** the reference app captures `auth.activeScope()` once at the start of the mutation and threads it through `context`. If a later callback re-read ambient `activeScope()` and the user (or a realtime race) had switched scope mid-flight, the rollback would patch the *wrong* cache bucket — a cross-scope corruption channel. Capture once, reuse.

---

## `useQueryClient()` + the imperative cache API

`useQueryClient()` returns the client from context. Use it inside hooks; use the module singleton outside the component tree (SSE handlers, etc.).

| Method | Use |
|---|---|
| `invalidateQueries({ queryKey })` | Mark matching queries stale and refetch the active ones. **Prefix-matches.** |
| `setQueryData(key, updater)` | Write the cache directly (optimistic updates, SSE-pushed rows). `updater` is a value or `(prev) => next`. |
| `getQueryData(key)` | Read the current cached value synchronously. |
| `setQueriesData({ queryKey }, updater)` | Patch *every* entry matching a prefix at once. |
| `prefetchQuery({ queryKey, queryFn })` | Warm the cache ahead of a render (hover, route preload). |
| `cancelQueries({ queryKey })` | Abort in-flight fetches (used before an optimistic write). |
| `removeQueries({ queryKey })` | Evict matching entries entirely. |

### Invalidation patterns — prefix matching

`invalidateQueries` matches by **key prefix**, so one call fans out across a family:

```ts
// Invalidate exactly one project's detail:
queryClient.invalidateQueries({ queryKey: scopedKeys.project(scopeArg, id) });

// Invalidate the project AND its children (targets, members, …) — the prefix
// matches every key that begins with [account, scope, 'project', id, …]:
queryClient.invalidateQueries({ queryKey: scopedKeys.project(scopeArg, id) });

// Invalidate every metrics slot in a scope (the bare factory is prefix-only):
queryClient.invalidateQueries({ queryKey: scopedKeys.metrics(scopeArg) });
```

> **Design "prefix-only" factories deliberately.** the reference app keeps bare-scope factories (`metrics`, `activity`, `handoffsAll`, `threadListAll`) whose *only* purpose is to be an invalidation prefix that matches every project-specific or filter-specific child slot. When a mutation doesn't know which exact child changed, it invalidates the prefix and lets prefix-matching do the fan-out.

Pushing a server-sent row straight into cache without a refetch (the reference app's SSE/doorbell path does this):

```ts
queryClient.setQueryData<ThreadRow>(scopedKeys.thread(scopeArg, id), (prev) =>
  prev ? { ...prev, ...patch } : prev
);
```

---

## `createInfiniteQuery` (pagination)

For cursor/page pagination with a shared cache. Same function-options idiom; adds `initialPageParam` + `getNextPageParam`, and `data` becomes `{ pages, pageParams }`.

```tsx
import { createInfiniteQuery } from '@tanstack/solid-query';

export function useActivityInfinite(filters: () => ActivityQueryFilters = () => ({})) {
  const auth = useAuthContext();
  return createInfiniteQuery(() => {
    const scope = auth.activeScope();
    return {
      queryKey: scope
        ? scopedKeys.activity(toScopeArg(scope), filters())
        : defineGlobalKey('activity', 'logged-out'),
      enabled: scope !== null,
      initialPageParam: null as string | null,
      queryFn: async ({ pageParam }) => {
        const res = await fetch(buildActivityUrl(filters(), pageParam));
        if (!res.ok) throw new Error('Failed to fetch activity');
        return res.json() as Promise<ListActivityResponse>;
      },
      getNextPageParam: (lastPage) => lastPage.nextCursor, // null => no next page
    };
  });
}

// consume:
const activity = useActivityInfinite();
<For each={activity.data?.pages.flatMap((p) => p.items)}>{(row) => <Row {...row} />}</For>
<button
  disabled={!activity.hasNextPage || activity.isFetchingNextPage}
  onClick={() => activity.fetchNextPage()}
>
  Load more
</button>
```

Key additions vs `createQuery`: `data.pages` (array of page payloads), `data.pageParams`, `fetchNextPage()`, `hasNextPage`, `isFetchingNextPage`, `fetchPreviousPage` / `hasPreviousPage`.

> **Sharing a prefix matters here too.** the reference app's `useActivityInfinite` deliberately reuses the *same* `scopedKeys.activity(...)` prefix as the non-infinite `useActivity`, so an SSE `activity_logged` invalidation refreshes every loaded page of both hooks with one call.

---

## Reactive `enabled` & dependent queries

Because the options function re-runs reactively, **dependent queries are automatic** — gate the dependent query's `enabled` on the first query's data, and read that data inside the function:

```tsx
// 1. Fetch the user.
const userQuery = createQuery(() => ({
  queryKey: ['user', userId()],
  queryFn: () => api.users.get(userId()),
}));

// 2. Fetch their projects — only once the user resolved.
const projectsQuery = createQuery(() => ({
  queryKey: ['projects', userQuery.data?.accountId],
  queryFn: () => api.projects.listForAccount(userQuery.data!.accountId),
  enabled: !!userQuery.data?.accountId, // tracked: re-evaluates when user resolves
}));
```

The second query reads `userQuery.data` *inside* its options function, so it tracks it. While `enabled` is false the query stays parked (`status: 'pending'`, `fetchStatus: 'idle'`, no fetch). The instant the user resolves, `enabled` flips true and the key is complete — the projects query fires. No `createEffect`, no manual orchestration.

> The same mechanism powers the logged-out fallback in every the reference app hook: `enabled: scope !== null` parks the query until auth resolves, and the key switches to a `defineGlobalKey('…','logged-out')` slot so a logged-out render never collides with real scoped data.

---

## `staleTime` vs `gcTime`, and option tiers

These two are the most-confused options. They answer different questions:

| | `staleTime` | `gcTime` (formerly `cacheTime`) |
|---|---|---|
| Question | "How long is fetched data **fresh**?" | "How long does an **unobserved** entry survive before deletion?" |
| Clock starts | At successful fetch | When the **last** observer unmounts |
| While fresh | Mounting the query serves cache with **no refetch** | n/a |
| When it elapses | Next mount/focus triggers a background refetch | The cache entry is garbage-collected |
| Default | `0` (always refetch on mount) | `300_000` (5 min) |

A query can be **stale but not collected** (data still cached, refetches on next mount) or **fresh** (served instantly). `gcTime` only matters for entries that currently have *zero* observers — a mounted query is never GC'd.

> **Common gotcha:** with the default `staleTime: 0`, every mount refetches. That's often not what you want for data that changes slowly. Set a sensible `staleTime` baseline (the reference app uses `60_000`) and tighten per-query only where freshness matters.

### Centralize policies as presets ("tiers")

Rather than scatter magic numbers, group `staleTime`/`gcTime`/`refetchOnWindowFocus` into named presets and spread one into each query. the reference app's `QUERY_TIERS`:

```ts
// query/tiers.ts (abridged)
export const QUERY_TIERS = {
  static:         { staleTime: Infinity,    gcTime: Infinity },                                 // invalidation-driven only
  doorbellBacked: { staleTime: 30 * 60_000, gcTime: 30 * 60_000, refetchOnWindowFocus: true },  // realtime-pushed; long safety net
  stable:         { staleTime: 5 * 60_000,  gcTime: 30 * 60_000 },                              // settings, sponsorship
  semiStable:     { staleTime: 60_000,      gcTime: 10 * 60_000 },                              // occasionally-edited project reads
  live:           { staleTime: 10_000,      gcTime: 5 * 60_000 },                               // co-edited, short poll fallback
  realtime:       { staleTime: 2_000,       gcTime: 2 * 60_000 },                               // timer-polled UI
} as const;

// usage:
createQuery(() => ({ queryKey, queryFn, ...QUERY_TIERS.semiStable }));
```

The win: freshness policy is a *vocabulary* ("this read is `semiStable`"), the numbers live in one file, and tuning is a single edit. the reference app layers a `gcTime` override on top (`getScopedGcTime`) so background-scope entries are evicted sooner than active-scope ones — but the tier preset is the baseline.

---

## Testing (brief)

Render under a **fresh** `QueryClient` + `QueryClientProvider` per test so cache never bleeds across cases, and **seed the cache** with `setQueryData` to simulate a successful fetch without mocking the network:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/solid-query';
import { renderHook, waitFor } from '@solidjs/testing-library';

function withClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } }, // no retries → deterministic failures
  });
  const wrapper = (props: { children: JSX.Element }) => (
    <QueryClientProvider client={queryClient}>{props.children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

it('reads a seeded project', async () => {
  const { queryClient, wrapper } = withClient();
  // Seed the cache as if the fetch already succeeded:
  queryClient.setQueryData(scopedKeys.project(SCOPE_ARG, 'p-1'), { id: 'p-1', name: 'Demo' });

  const { result } = renderHook(() => useEditProject(() => 'p-1'), { wrapper });
  await waitFor(() => expect(result.project()?.name).toBe('Demo'));
});
```

the reference app's hook tests mock `useAuthContext` to a fixed scope and stub `globalThis.fetch`, then assert URL/verb/body *and* the cache effect (which keys got invalidated) against a real `QueryClient`. Set `retry: false` so a deliberately-failed `queryFn` surfaces `isError` immediately instead of after backoff. See the testing chapter for the full harness.

---

## When to use Solid Query vs `createResource` vs a plain signal

| Scenario | Use |
|---|---|
| Server value read in **multiple** components, deduped + cached | **`createQuery`** |
| Background refetch / stale-while-revalidate / focus + reconnect refetch | **`createQuery`** |
| Write that must refresh related reads | **`createMutation`** + `invalidateQueries` |
| Optimistic UI with rollback | **`createMutation`** (`onMutate` + `setQueryData` + `onError`) |
| Pagination / infinite scroll over a shared cache | **`createInfiniteQuery`** |
| One-off async value, **local** to a component, no sharing/caching | `createResource` |
| Async value you fully own and want raw control over (no cache policy) | `createResource` |
| Pure **client** state (modal open, form draft, selection, counter) | `createSignal` / `createStore` — never a query |
| Derived value computed from other reactive state | `createMemo` |

---

## Cheat-sheet

```tsx
import {
  QueryClient, QueryClientProvider, useQueryClient,
  createQuery, createMutation, createInfiniteQuery,
} from '@tanstack/solid-query';

// options are ALWAYS a function returning the object — that's the reactivity boundary
const q = createQuery(() => ({
  queryKey: ['thing', id()],            // tracked: read signals INSIDE the fn
  queryFn: ({ signal }) => fetch(url, { signal }).then((r) => r.json()),
  enabled: !!id(),
  staleTime: 60_000,
  gcTime: 300_000,
}));
// read off the proxy in tracking scope — NEVER destructure:
q.data; q.isPending; q.isError; q.error; q.isFetching; q.refetch();

const m = createMutation(() => ({
  mutationFn: (vars) => api.write(vars),
  onMutate: async (vars) => { /* cancel + snapshot + optimistic setQueryData */ },
  onError: (e, vars, ctx) => { /* rollback from ctx */ },
  onSettled: () => qc.invalidateQueries({ queryKey: ['thing'] }),
}));
m.mutate(vars); await m.mutateAsync(vars); m.isPending;

const qc = useQueryClient();
qc.invalidateQueries({ queryKey: ['thing'] }); // prefix-matches
qc.setQueryData(['thing', id], (prev) => next);
qc.getQueryData(['thing', id]);
qc.prefetchQuery({ queryKey, queryFn });
qc.cancelQueries({ queryKey }); qc.removeQueries({ queryKey });
```
