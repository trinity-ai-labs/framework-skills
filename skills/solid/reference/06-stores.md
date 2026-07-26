# Stores

Fine-grained reactivity over nested objects and arrays.

## Why stores exist

A `createSignal` holds a single value. When it changes, every computation that read it re-runs — the whole value is replaced. That is fine for primitives or small, flat objects, but it is lossy for structured data: changing one field of a 500-entry todo list should not re-render every row.

`createStore` wraps your object in a **proxy** that instruments every property access. Reading `store.user.name` subscribes the running computation to *just that path* — not to the parent object, not to sibling keys. Setting `setStore("user", "name", "Alice")` notifies only the computations that read `store.user.name`. No diffing, no virtual DOM, just a surgical signal per property node.

```
store.todos[2].done  →  subscribes to todos[2].done only
setStore("todos", 2, "done", true)  →  notifies only readers of todos[2].done
```

This is the right primitive whenever you have:
- Deeply nested state (settings, user objects, tree data)
- Lists where you update individual items
- State shared across components that each care about different sub-paths

---

## Contents

- [Why stores exist](#why-stores-exist)
- [`createStore<T>(initialValue)` — basics](#createstoretinitialvalue-basics)
- [`setStore` — update forms](#setstore-update-forms)
- [`produce(fn)` — Immer-style mutable drafts](#producefn-immer-style-mutable-drafts)
- [`reconcile(value, options?)` — diff-and-merge external data](#reconcilevalue-options-diff-and-merge-external-data)
- [`unwrap(store)` — escape the proxy](#unwrapstore-escape-the-proxy)
- [`createMutable(obj)` — direct assignment](#createmutableobj-direct-assignment)
- [Nested reactivity and arrays](#nested-reactivity-and-arrays)
- [Full example — todo app store](#full-example-todo-app-store)
- [Store index / sub-store from context](#store-index-sub-store-from-context)
- [See also](#see-also)


## `createStore<T>(initialValue)` — basics

```ts
import { createStore } from "solid-js/store"

type Todo = { id: number; text: string; done: boolean }
type State = { todos: Todo[]; filter: "all" | "active" | "done" }

const [state, setStore] = createStore<State>({
  todos: [],
  filter: "all",
})
```

**Return value:** `[store, setStore]`
- `store` — a reactive **proxy**. Read through it like a plain object: `state.todos`, `state.todos[0].done`.
- `setStore` — the setter function with multiple overloads (see below).

`store` is typed as `Store<T>`, which is `T` with no special markers — you access it the same way as a plain object. The reactivity is in the proxy, not the type.

### Never destructure a store

The same rule as props applies: destructuring reads a value *once* from the proxy and loses the reactive subscription.

```tsx
// ❌ loses reactivity — name is a frozen string
const { name } = state.user
return <div>{name}</div>

// ✅ access by path — reactive
return <div>{state.user.name}</div>
```

If you need to pass a sub-object to a child component, pass the whole store or a getter that reads the path live:

```tsx
// ✅ pass a getter (accessor) instead of a destructured value
<UserCard name={() => state.user.name} />

// ✅ or pass the store and let the child access the path
<UserCard store={state} />
```

---

## `setStore` — update forms

`setStore` is a variadic function: you pass a sequence of keys (the path), then a value or updater at the end. It is the only way to write to a store; never mutate `store` directly.

### 1. Root object replace / merge

```ts
// Merge fields at the root — other fields are preserved
setStore({ filter: "active" })

// Replace the entire root (pass the whole new object)
setStore({ todos: [], filter: "all" })
```

### 2. Path — set a nested value

Pass keys as individual string/number arguments, with the new value last:

```ts
// setStore(...keys, value)
setStore("filter", "done")
setStore("todos", 0, "done", true)
setStore("user", "address", "city", "Cape Town")
```

Keys can be strings (object keys) or numbers (array indices).

### 3. Updater function — compute next value from previous

Replace the final value with a function that receives the current value and returns the next:

```ts
setStore("count", (prev) => prev + 1)
setStore("todos", 0, "text", (t) => t.trim())
```

### 4. Object merge at a path

Pass a partial object as the setter — its keys are merged into the target:

```ts
// Merge { name, age } into state.user — other user fields survive
setStore("user", { name: "Alice", age: 30 })
```

### 5. Array index — numeric key

```ts
setStore("todos", 2, "done", true)
setStore("todos", 2, { text: "Updated text", done: false })
```

### 6. Array filter selector — update all items matching a predicate

Pass a **function** in a key position to select matching items:

```ts
// Mark all done todos as archived
setStore("todos", (todo) => todo.done, "archived", true)

// Zero the score of every losing team
setStore("teams", (team) => team.score < 0, "score", 0)
```

The filter function receives `(item, index)` and returns a boolean. Every matching element is updated.

### 7. Array range — `StorePathRange`

```ts
// Update indices 2 through 5
setStore("todos", { from: 2, to: 5 }, "done", true)

// Every other item starting at index 0
setStore("todos", { from: 0, by: 2 }, "highlighted", true)
```

`StorePathRange` has optional `from`, `to`, `by` fields (all numbers, inclusive/exclusive as JS conventions).

### 8. Array of keys — update multiple specific indices

```ts
// Update items at indices 1, 3, 7
setStore("todos", [1, 3, 7], "selected", true)
```

---

## `produce(fn)` — Immer-style mutable drafts

For complex nested updates where the path API becomes unwieldy, `produce` gives you a mutable **draft** — an object you can mutate imperatively. The mutations are applied to the store atomically.

```ts
import { produce } from "solid-js/store"

// Move a todo from one list to another
setStore(
  produce((draft) => {
    const todo = draft.todos.splice(fromIndex, 1)[0]
    draft.archived.push(todo)
  })
)

// Nested mutation with conditions
setStore(
  produce((draft) => {
    for (const todo of draft.todos) {
      if (todo.priority === "high") {
        todo.done = false
        todo.flagged = true
      }
    }
  })
)
```

`produce` is especially useful when:
- You need to move/reorder items in arrays
- The update touches multiple paths that are hard to express as separate `setStore` calls
- The new value at a path depends on sibling values in the same transaction

`produce` returns a `(state: T) => T` function, so you can also compose it:

```ts
const toggleAll = produce<State>((draft) => {
  draft.todos.forEach((t) => { t.done = !t.done })
})

// Reuse in multiple places
setStore(toggleAll)
```

### `produce` vs path-set guidance

| Situation | Prefer |
|---|---|
| Single field at a known path | Path set: `setStore("user", "name", "X")` |
| Compute next value from previous | Updater: `setStore("count", c => c+1)` |
| Merge a few keys into an object | Object merge: `setStore("user", { name, age })` |
| Update all items matching a condition | Filter selector: `setStore("items", fn, "field", val)` |
| Move/splice items across arrays | `produce` |
| Multiple nested mutations in one transaction | `produce` |
| Update logic reads sibling state | `produce` |

---

## `reconcile(value, options?)` — diff-and-merge external data

When you receive new data from the network (a fetch response, a query result, a WebSocket message), naively replacing the store node would dispose all child subscriptions and recreate them, causing every consumer to re-run. `reconcile` diffs the new value against the existing store tree and applies only the changes, preserving identity for unchanged nodes.

```ts
import { reconcile } from "solid-js/store"

const [users, setUsers] = createStore<User[]>([])

async function refresh() {
  const data = await fetchUsers()
  // Only rows that actually changed get notified
  setUsers(reconcile(data, { key: "id" }))
}
```

### Options

```ts
type ReconcileOptions = {
  key?: string | null   // identity key for object matching (default: "id")
  merge?: boolean       // false (default) = replace unmapped keys; true = merge/preserve extras
}
```

- **`key`** — the property used to match objects in arrays by identity. Items with the same `key` value are updated in place rather than replaced. Set to `null` to match by position.
- **`merge`** — when `true`, keys present in the store but absent from the new value are preserved (merge semantics). When `false` (default), extra keys are removed (replace semantics).

### Canonical pattern: resource or query result → store

```ts
const [data] = createResource(fetchUsers)

createEffect(() => {
  const result = data()
  if (result) setUsers(reconcile(result, { key: "id" }))
})
```

> **Note.** In the reference app, server data flows through `@tanstack/solid-query` — `createQuery` manages the cache and delivers new snapshots. When you need a locally editable copy of that data (e.g., an optimistic list), store + `reconcile` is the right pattern: sync from the query result into a store, edit locally, merge back. For read-only display you usually just render from the query accessor directly.

---

## `unwrap(store)` — escape the proxy

`unwrap` returns the raw, non-proxied object underlying a store. Use it when you need to:
- Serialize to JSON (`JSON.stringify(unwrap(state))`)
- Pass the data to a library that doesn't expect a proxy
- Log the true object identity in debugging

```ts
import { unwrap } from "solid-js/store"

const [state, setStore] = createStore({ todos: [{ id: 1, text: "Buy milk" }] })

const raw = unwrap(state)
// raw === the original plain object (not the proxy)
// JSON.stringify(raw) works correctly

console.log(state === raw)         // false — state is the proxy
console.log(unwrap(state) === raw) // true
```

> Reading from `unwrap(state)` is **non-reactive** — it bypasses all tracking. Only use it when you intentionally want a one-time snapshot.

---

## `createMutable(obj)` — direct assignment

`createMutable` creates a proxy where you can **assign directly** to mutate state, like a plain object:

```ts
import { createMutable } from "solid-js/store"

const store = createMutable({ count: 0, name: "Alice" })

// Mutation via direct assignment — reactive
store.count++
store.name = "Bob"
```

`modifyMutable` applies a modifier function (like `produce` or `reconcile`) to a mutable store:

```ts
import { modifyMutable, produce } from "solid-js/store"

modifyMutable(store, produce((draft) => {
  draft.count += 10
}))
```

### When to avoid `createMutable`

Most apps should not use `createMutable`. It makes mutation too easy to do accidentally from outside a component, breaking the one-way data flow that makes Solid apps predictable.

| | `createStore` + `setStore` | `createMutable` |
|---|---|---|
| Mutation model | Explicit setter calls | Direct assignment anywhere |
| Encapsulation | Natural — only code with `setStore` can mutate | Anyone holding the ref can mutate |
| Traceability | Easy to find all write sites | Mutations can happen anywhere |
| Ecosystem fit | Standard Solid idiom | Third-party / interop use |

**Reach for `createMutable` when:** integrating with a third-party library that expects a plain mutable object, or authoring a class-style store where the mutation model is intentionally open. For all normal app state, use `createStore`.

---

## Nested reactivity and arrays

Store proxies are **deep** — nested objects and arrays are also wrapped. Reactivity tracks at every node in the tree.

```ts
const [state, setStore] = createStore({
  board: {
    columns: [
      { id: "todo", cards: [{ id: 1, title: "Design" }] },
      { id: "done", cards: [] },
    ],
  },
})

// Reading state.board.columns[0].cards[0].title subscribes to just that leaf
// setStore("board", "columns", 0, "cards", 0, "title", "Implement")
// — notifies only readers of that exact node
```

### Arrays in stores with `<For>`

```tsx
import { For } from "solid-js"
import { createStore } from "solid-js/store"

type Item = { id: number; name: string; selected: boolean }

const [state, setStore] = createStore<{ items: Item[] }>({ items: [] })

function List() {
  return (
    <For each={state.items}>
      {(item) => (
        <div
          class={item.selected ? "selected" : ""}
          onClick={() => setStore("items", (i) => i.id === item.id, "selected", (s) => !s)}
        >
          {item.name}
        </div>
      )}
    </For>
  )
}
```

`<For>` keys by item **reference**. Because the store proxy preserves item identity for unchanged items, only the row whose data actually changed re-renders. Toggling `selected` on item 3 updates only that row.

> **`<For>` vs `<Index>`:** Use `<For>` with stores (items have stable identity). Use `<Index>` only for position-keyed lists where items are primitives or frequently reordered by index.

---

## Full example — todo app store

```tsx
import { createStore, produce } from "solid-js/store"
import { For, Show } from "solid-js"

type Todo = { id: number; text: string; done: boolean }

const [state, setStore] = createStore<{ todos: Todo[]; nextId: number }>({
  todos: [],
  nextId: 1,
})

function addTodo(text: string) {
  setStore(
    produce((draft) => {
      draft.todos.push({ id: draft.nextId++, text, done: false })
    })
  )
}

function toggleTodo(id: number) {
  setStore("todos", (t) => t.id === id, "done", (d) => !d)
}

function removeDone() {
  setStore("todos", (todos) => todos.filter((t) => !t.done))
}

function TodoApp() {
  let input!: HTMLInputElement

  return (
    <div>
      <input ref={input} placeholder="New todo" />
      <button onClick={() => { addTodo(input.value); input.value = "" }}>
        Add
      </button>
      <button onClick={removeDone}>Remove done</button>

      <For each={state.todos}>
        {(todo) => (
          <div>
            <input
              type="checkbox"
              checked={todo.done}
              onChange={() => toggleTodo(todo.id)}
            />
            <span style={{ "text-decoration": todo.done ? "line-through" : "none" }}>
              {todo.text}
            </span>
          </div>
        )}
      </For>

      <Show when={state.todos.length === 0}>
        <p>No todos yet.</p>
      </Show>
    </div>
  )
}
```

---

## Store index / sub-store from context

Stores are plain values — you can provide them through context just like any other value:

```tsx
import { createContext, useContext } from "solid-js"
import { createStore } from "solid-js/store"

const [state, setStore] = createStore({ theme: "light" as "light" | "dark" })

const StoreContext = createContext({ state, setStore })

export function useAppStore() {
  return useContext(StoreContext)
}
```

---

## See also

- [02-reactivity.md](02-reactivity.md) — signals, memos, effects, how tracking works
- [04-control-flow.md](04-control-flow.md) — `<For>` vs `<Index>`, `<Show>`, control flow components
- [07-async-and-resources.md](07-async-and-resources.md) — `createResource`, `reconcile` with fetched data
- [08-context.md](08-context.md) — providing stores to a component tree
- [15-pitfalls.md](15-pitfalls.md) — destructuring traps, the most common store mistakes
