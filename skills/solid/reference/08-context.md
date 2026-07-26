# Context

How to share state across a component tree without prop-drilling. Solid's context is not reactive on its own — you thread reactive values *through* it, and consumers subscribe to those values directly via the normal signal/store mechanisms.

Verified against **solid-js v1.9.x** (`packages/solid/src/reactive/signal.ts`, `packages/solid/src/render/component.ts`).

---

## Contents

- [First: do you actually need context?](#first-do-you-actually-need-context)
- [The primitives](#the-primitives)
- [`createContext` — default value vs. required provider](#createcontext-default-value-vs-required-provider)
- [The typed-provider pattern — a complete example](#the-typed-provider-pattern-a-complete-example)
- [Why context value must be reactive](#why-context-value-must-be-reactive)
- [Performance characteristics](#performance-characteristics)
- [Provider nesting and composition](#provider-nesting-and-composition)
- [Context and ownership](#context-and-ownership)
- [Cheat sheet](#cheat-sheet)
- [See also](#see-also)


## First: do you actually need context?

Solid has three ways to share state without prop-drilling, and context is the heaviest. Because a signal is not tied to a component instance, **a module-level signal is a legitimate global store in Solid** — this is the biggest departure from React, where a module-level `useState` is impossible and context is the only door.

| Want | Use | Why |
| --- | --- | --- |
| One instance for the whole app, no per-subtree variation, no SSR | **Module-level signal/store** | Simplest thing that works. `export const [theme, setTheme] = createSignal("dark")` — import it anywhere. No provider, no `useContext`, no undefined check. |
| Same, but it owns effects/timers/subscriptions that need disposal | **`createRoot` singleton** | A bare module-level `createEffect` has no owner, never disposes, and warns. `createRoot` gives the singleton a lifetime you control. → [Lifecycle & ownership](05-lifecycle-and-ownership.md) · [Pitfalls #13](15-pitfalls.md) |
| **Different values for different subtrees**, or the value depends on props/route, or you need to swap it in tests, or SSR | **Context** | This is the only one of the three that can vary by position in the tree. Everything below. |

**The deciding question is not "is it global?" — it's "does any part of the tree need a *different* value?"** If the answer is no and you never render two of them, a module-level signal is not a shortcut, it is the correct choice; reaching for a provider adds indirection that buys nothing.

Two caveats that push you back toward context: module-level state is **shared across requests under SSR** (out of scope for this skill, but fatal if you later add it), and it is **shared across tests in the same module registry**, so tests must reset it explicitly.

---

## The primitives

```ts
import { createContext, useContext } from "solid-js"
import type { Context } from "solid-js"

// No default value → T | undefined; TypeScript infers Context<T | undefined>
function createContext<T>(defaultValue?: undefined, options?: { name?: string }): Context<T | undefined>

// With default → T; never undefined
function createContext<T>(defaultValue: T, options?: { name?: string }): Context<T>

function useContext<T>(context: Context<T>): T
```

A `Context<T>` object has three members:

```ts
interface Context<T> {
  id: symbol                          // unique identity key
  Provider: (props: { value: T; children: JSX.Element }) => JSX.Element
  defaultValue: T
}
```

`createContext` creates a context object. `useContext` looks up the nearest provided value walking up the reactive owner tree.

---

## `createContext` — default value vs. required provider

### With a sensible default

Use when a reasonable fallback exists and the context is optional infrastructure:

```ts
import { createContext, useContext } from "solid-js"

const ThemeCtx = createContext<"light" | "dark">("light")
//    ^? Context<"light" | "dark">

// useContext always returns "light" | "dark" — never undefined
const theme = useContext(ThemeCtx)  // "light" if no Provider above it
```

### Without a default (undefined + runtime guard)

Use when the context is mandatory — consuming it outside a provider is a programmer error:

```ts
import { createContext } from "solid-js"

// No default → Context<AuthState | undefined>
const AuthCtx = createContext<AuthState>()

// useContext returns AuthState | undefined — callers must guard
```

The canonical pattern is to hide the raw `useContext` call inside a `useAuth()` hook that throws immediately if the value is absent:

```ts
function useAuth(): AuthState {
  const ctx = useContext(AuthCtx)
  if (ctx === undefined) throw new Error("useAuth() must be called inside <AuthProvider>")
  return ctx
}
```

This converts a silent `undefined` into a loud, actionable error at the call site.

> **`options.name`** is a dev-mode-only hint for the Solid devtools. It has no runtime effect in production.

---

## The typed-provider pattern — a complete example

The full idiom bundles context creation, provider component, and accessor hook into a single file:

```tsx
// auth-context.tsx
import { createContext, useContext, createSignal, type JSX } from "solid-js"

// ── Types ─────────────────────────────────────────────────────────────────────

interface User {
  id: string
  name: string
  email: string
}

interface AuthState {
  // Accessors — call them to read the current value
  user: () => User | null
  isAuthenticated: () => boolean
  // Actions
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
}

// ── Context ───────────────────────────────────────────────────────────────────

// No default → undefined signals "used outside provider"
const AuthCtx = createContext<AuthState>()

// ── Provider ──────────────────────────────────────────────────────────────────

export function AuthProvider(props: { children: JSX.Element }) {
  const [user, setUser] = createSignal<User | null>(null)

  const signIn = async (email: string, password: string) => {
    const data = await fetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }).then(r => r.json())
    setUser(data.user)
  }

  const signOut = () => {
    setUser(null)
    fetch("/api/auth/logout", { method: "POST" })
  }

  // The value object is stable — it holds signal accessors, not snapshots
  const value: AuthState = {
    user,                          // () => User | null
    isAuthenticated: () => user() !== null,
    signIn,
    signOut,
  }

  return (
    <AuthCtx.Provider value={value}>
      {props.children}
    </AuthCtx.Provider>
  )
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx)
  if (ctx === undefined) {
    throw new Error("useAuth() must be used inside <AuthProvider>")
  }
  return ctx
}
```

Usage anywhere in the tree:

```tsx
import { Show } from "solid-js"
import { useAuth } from "./auth-context"

function Header() {
  const auth = useAuth()

  return (
    <header>
      <Show when={auth.isAuthenticated()} fallback={<a href="/login">Sign in</a>}>
        <span>Hello, {auth.user()?.name}</span>
        <button onClick={auth.signOut}>Sign out</button>
      </Show>
    </header>
  )
}
```

`auth.user()` and `auth.isAuthenticated()` are signal accessors — any reactive scope that calls them subscribes to the underlying signal. When `setUser` fires, only the computations that read `user()` or `isAuthenticated()` update. The context lookup itself does not cause any re-evaluation.

---

## Why context value must be reactive

Context does **not** intercept reads or track changes. `useContext(Ctx)` is a single lookup that returns whatever was passed to `<Ctx.Provider value={...}>` at the time the component ran. If you pass a plain object or a primitive, consumers receive a snapshot frozen at mount time:

```tsx
// ❌ snapshot — consumers never see count updates
function BadProvider(props: { children: JSX.Element }) {
  const [count, setCount] = createSignal(0)
  return (
    <CountCtx.Provider value={count()}>   {/* reads count() once, at mount */}
      {props.children}
    </CountCtx.Provider>
  )
}

// ✅ accessor — consumers call count() and subscribe live
function GoodProvider(props: { children: JSX.Element }) {
  const [count, setCount] = createSignal(0)
  return (
    <CountCtx.Provider value={count}>     {/* passes the accessor function */}
      {props.children}
    </CountCtx.Provider>
  )
}
```

**The rule:** pass reactive containers (signal accessors, stores, functions that read signals), not the current values of those containers.

### Stores as context values

Stores work well for structured shared state because they're already reactive objects:

```tsx
import { createContext, useContext, createStore, type JSX } from "solid-js"
import { type SetStoreFunction } from "solid-js/store"

interface AppSettings {
  theme: "light" | "dark"
  language: string
  notifications: boolean
}

type SettingsCtxValue = [
  settings: AppSettings,
  setSettings: SetStoreFunction<AppSettings>
]

const SettingsCtx = createContext<SettingsCtxValue>()

export function SettingsProvider(props: { children: JSX.Element }) {
  const [settings, setSettings] = createStore<AppSettings>({
    theme: "light",
    language: "en",
    notifications: true,
  })

  return (
    <SettingsCtx.Provider value={[settings, setSettings]}>
      {props.children}
    </SettingsCtx.Provider>
  )
}

export function useSettings(): SettingsCtxValue {
  const ctx = useContext(SettingsCtx)
  if (!ctx) throw new Error("useSettings() must be used inside <SettingsProvider>")
  return ctx
}
```

Consumers destructure the store and are subscribed at field granularity — reading `settings.theme` tracks only theme changes:

```tsx
function ThemeToggle() {
  const [settings, setSettings] = useSettings()
  return (
    <button onClick={() => setSettings("theme", t => t === "light" ? "dark" : "light")}>
      {settings.theme}
    </button>
  )
}
```

---

## Performance characteristics

Context in Solid does **not** trigger re-renders or even reactive updates. This is different from React's context, which schedules a re-render in every consumer whenever the provider value reference changes.

In Solid, context is just a value lookup on the owner tree. Updating the context value itself (e.g. replacing `<Ctx.Provider value={newObj}>` with a different object) does cause the Provider's `createRenderEffect` to re-run, which can re-create children. But the ordinary reactive case — passing signal accessors and updating signals — has no overhead at the context layer. Updates flow directly through the reactive graph: the signal notifies its subscribers, which happen to be DOM bindings or effects inside consumers, with no indirection through context.

**Practical implication:** you do not need to split contexts for performance reasons. In React, splitting contexts avoids "all consumers re-rendering when any part of a fat context changes." In Solid, there is no such re-render. Split contexts for **ergonomics and ownership clarity** — keeping `AuthProvider` separate from `SettingsProvider` is about logical organization, not about preventing cascading re-renders.

```tsx
// ✅ Fine in Solid — no render-perf reason to split
const AppCtx = createContext<{ auth: AuthState; settings: AppSettings; theme: ThemeState }>()

// ✅ Also fine — use when logical separation is clearer
const AuthCtx    = createContext<AuthState>()
const SettingsCtx = createContext<AppSettings>()
const ThemeCtx   = createContext<ThemeState>()
```

---

## Provider nesting and composition

Providers nest freely. `useContext` always returns the value from the **nearest** ancestor provider with a matching `id`. This makes overrides trivially composable:

```tsx
// Outer theme: dark
<ThemeCtx.Provider value="dark">
  <Sidebar />        {/* sees "dark" */}

  {/* Override just this subtree */}
  <ThemeCtx.Provider value="light">
    <Modal />        {/* sees "light" */}
  </ThemeCtx.Provider>
</ThemeCtx.Provider>
```

### A production provider stack

the reference app wraps the app in a sequence of providers at the root:

```tsx
// src/app.tsx (simplified)
render(
  () => (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AuthProvider>
            <Router>
              <App />
            </Router>
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  ),
  document.getElementById("root")!
)
```

Each provider creates its reactive state (signals, stores, query client) and makes it available via a typed hook. The order matters only when providers depend on each other — e.g., `<AuthProvider>` sits inside `<QueryClientProvider>` because auth logic uses `@tanstack/solid-query` queries internally. Independent providers can be in any order.

> **Organizing the stack.** A common pattern is to extract provider composition into a dedicated component — `<AppProviders>` — so `render()` stays clean and the stack can be reused in tests without the router:

```tsx
function AppProviders(props: { children: JSX.Element }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AuthProvider>
            {props.children}
          </AuthProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
```

---

## Context and ownership

Providers set context on the reactive owner tree, not on the DOM tree. When `<Ctx.Provider value={v}>` renders, it calls:

```ts
Owner!.context = { ...Owner!.context, [id]: props.value }
```

That owner slot is inherited by all child computations created within the provider's subtree. `useContext` walks up `Owner.context` to find the matching `id`. The key insight: **context lives on reactive owners, not on JSX elements**. If you create a child computation inside `runWithOwner(owner, fn)` and that owner is from inside a provider, `useContext` will find the provider's value correctly — even if you're in an async callback or a setTimeout.

```tsx
import { createContext, useContext, getOwner, runWithOwner, type JSX } from "solid-js"

const FlagCtx = createContext(false)

function Inner() {
  const owner = getOwner()

  fetch("/api").then(() => {
    runWithOwner(owner, () => {
      // ✅ FlagCtx is found because `owner` is inside <FlagCtx.Provider>
      const flag = useContext(FlagCtx)
      console.log(flag)  // true
    })
  })

  return <div />
}

function App() {
  return (
    <FlagCtx.Provider value={true}>
      <Inner />
    </FlagCtx.Provider>
  )
}
```

The inverse: if you create a `createRoot` without passing `detachedOwner`, the root has no parent owner and `useContext` will return the default value, not any ancestor provider's value:

```ts
createRoot((dispose) => {
  // ❌ No ancestor owner — useContext returns the context default
  const flag = useContext(FlagCtx)   // false (the default), not what the Provider set
})

// ✅ Pass the captured owner so context lookups traverse the provider chain
createRoot((dispose) => {
  const flag = useContext(FlagCtx)   // true
}, getOwner())
```

---

## Cheat sheet

| Goal | Pattern |
|---|---|
| Create a context with a default | `const Ctx = createContext<T>(defaultValue)` |
| Create a required-provider context | `const Ctx = createContext<T>()` — default is `undefined` |
| Provide a value | `<Ctx.Provider value={reactiveValue}>` |
| Consume safely with a guard | `useContext(Ctx) ?? throw new Error(...)` — wrap in a custom hook |
| Pass reactive state | Pass signal accessors or stores — not `signal()` snapshots |
| Override in a subtree | Nest a second `<Ctx.Provider>` — nearest ancestor wins |
| Context in async code | Capture `getOwner()` before the await, then `runWithOwner(owner, ...)` |
| Context in a detached root | Pass `getOwner()` as `createRoot`'s second argument |
| Dev-mode label | `createContext(default, { name: "MyCtx" })` |

---

## See also

- [01-mental-model.md](01-mental-model.md) — components run once; how the reactive owner tree is built
- [05-lifecycle-and-ownership.md](05-lifecycle-and-ownership.md) — `getOwner`, `runWithOwner`, `createRoot` — the mechanisms that thread context across async and detached scopes
- [06-stores.md](06-stores.md) — stores as context values for structured shared state
