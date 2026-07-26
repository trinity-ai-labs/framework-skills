# Context, Services & Layers

> **When you reach for this:** any time an Effect needs a dependency — a database, a config, an API client, a logger. This is how you declare what a program *requires* (`R`), implement those requirements as services, and wire them together into a runnable app with `R = never`. Dependency injection is the spine of every non-trivial Effect application.

Verified against the **Effect v3** source (`packages/effect/src/{Context,Layer,Effect}.ts`).

---

## Contents

- [The `R` channel (Requirements / Context)](#the-r-channel-requirements-context)
- [`Context` + `Tag`](#context-tag)
- [Defining services](#defining-services)
- [Accessing services](#accessing-services)
- [`Layer<ROut, E, RIn>`](#layerrout-e-rin)
- [Providing layers to effects](#providing-layers-to-effects)
- [Full worked example: Config → Database → UserRepo → UserService](#full-worked-example-config-database-userrepo-userservice)
- [Swapping implementations (tests / environments)](#swapping-implementations-tests-environments)
- [Config integration (brief)](#config-integration-brief)
- [Cheat sheet](#cheat-sheet)
- [See also](#see-also)


## The `R` channel (Requirements / Context)

Every effect is `Effect<A, E, R>`:

- `A` — success value
- `E` — expected (typed) error
- `R` — the **requirements**: the set of services the effect needs in its environment before it can run

`R` is a *type-level set* (a union of tag identifiers) describing what you must supply before the effect can run. In v3 the `Effect` interface declares it covariantly (`Effect<out A, out E, out R>`), but read it operationally as a requirement checklist: requirements **accumulate** as a union through composition, and providing one **removes** it.

Requirements **accumulate** automatically through composition. When you combine effects, their `R` channels union:

```ts
import { Effect } from "effect"

declare const a: Effect.Effect<number, never, Database>
declare const b: Effect.Effect<string, never, HttpClient>

// R unions to `Database | HttpClient`
const program = Effect.gen(function* () {
  const n = yield* a
  const s = yield* b
  return `${s}:${n}`
})
//    ^? Effect<string, never, Database | HttpClient>
```

Providing a dependency **eliminates it** from `R` (via `Exclude<R, ...>` in every `provide*` signature). A program is runnable only once `R = never`:

```ts
declare const DatabaseLive: Layer.Layer<Database>

const runnable = program.pipe(
  Effect.provide(DatabaseLive),          // removes Database from R
  Effect.provideService(HttpClient, /* impl */ undefined as any) // removes HttpClient
)
//    ^? Effect<string, never, never>  ← fully wired

// Effect.runPromise / runSync ONLY accept Effect<A, E, never>.
```

❌ Don't call `Effect.runPromise(program)` while `R` is non-`never` — it's a type error telling you a dependency is unmet.
✅ Do read the `R` channel as a checklist of what's still missing.

---

## `Context` + `Tag`

A `Context<Services>` is the runtime table that backs `R`. Internally it is a `Map<string, any>` keyed by **`tag.key`** (a unique string), mapping each `Tag` to its implementation. You rarely build one by hand — `Layer` does it for you — but understanding it demystifies everything else.

### Tag identity is the unique string key

Because the context maps by `tag.key`, **the string identifier IS the identity**. Two tags with the same key refer to the same slot. `GenericTag` even dedups by key:

```ts
import { Context } from "effect"

Context.GenericTag("PORT").key === Context.GenericTag("PORT").key // true
```

✅ Do namespace keys to avoid collisions across packages: `"App/Database"`, `"@myorg/Mailer"`.
❌ Don't reuse a bare key like `"Config"` in two unrelated modules — they'll clash silently in the context map.

### Building tags

```ts
import { Context, Effect } from "effect"

// 1. GenericTag — value-level, often paired with a separate interface
interface Port { readonly PORT: number }
const Port = Context.GenericTag<Port>("App/Port")        // Tag<Port, Port>
const Port2 = Context.GenericTag<"PortId", Port>("App/Port") // distinct Id and Service

// 2. Context.Tag class — the idiomatic "tag = class" form (Self generic = the class)
class Timeout extends Context.Tag("App/Timeout")<
  Timeout,                       // Self / Identifier
  { readonly TIMEOUT: number }   // Service shape
>() {}
```

### Context operations

```ts
import { Context, pipe } from "effect"

const ctx0 = Context.empty()                         // Context<never>
const ctx1 = Context.make(Port, { PORT: 8080 })      // Context<Port>
const ctx2 = pipe(ctx1, Context.add(Timeout, { TIMEOUT: 5000 })) // Context<Port | Timeout>

Context.get(ctx2, Port)        // { PORT: 8080 }  — type-checked: tag must be in Services
Context.unsafeGet(ctx2, Port)  // throws if absent (no type guarantee)
Context.getOption(ctx2, Port)  // Option<{ PORT: number }>

const merged = Context.merge(ctx1, Context.make(Timeout, { TIMEOUT: 1 })) // Context<Port | Timeout>
const all = Context.mergeAll(ctx1, ctx2)             // n-ary merge (since 3.12.0)
const onlyPort = pipe(ctx2, Context.pick(Port))      // Context<Port>
const noPort = pipe(ctx2, Context.omit(Port))        // Context<Timeout>
```

---

## Defining services

There are two patterns. **Prefer `Effect.Service`** — it bundles the tag *and* a ready-made layer in one declaration. Reach for `Context.Tag` when you want to manage the layer separately or have multiple implementations from the start.

### Recommended: `Effect.Service` (since 3.9.0)

`class Foo extends Effect.Service<Foo>()("App/Foo", { ... }) {}` generates:

- a `Context.Tag<Foo, Foo>` (the class itself is the tag — `yield* Foo`)
- a `Foo.Default` layer that builds the service
- `Foo.DefaultWithoutDependencies` *when* `dependencies` is set
- a `Foo.make(impl)` constructor and `Foo.use(fn)` accessor
- optional generated accessor methods when `accessors: true`

The `Self` generic is **mandatory** (`Effect.Service<Foo>()`). Omitting it produces a `MissingSelfGeneric` type error.

Four ways to build the implementation:

```ts
import { Effect } from "effect"

// succeed — a static value, no effects
class Prefix extends Effect.Service<Prefix>()("App/Prefix", {
  succeed: { prefix: "PRE" }
}) {}

// sync — lazily computed, still pure
class Clock extends Effect.Service<Clock>()("App/Clock", {
  sync: () => ({ now: () => Date.now() })
}) {}

// effect — construction can use other effects / services
class Logger extends Effect.Service<Logger>()("App/Logger", {
  accessors: true,
  effect: Effect.gen(function* () {
    const { prefix } = yield* Prefix          // depends on Prefix at build time
    return {
      info: (message: string) =>
        Effect.sync(() => console.log(`[${prefix}] ${message}`))
    }
  }),
  dependencies: [Prefix.Default]               // auto-provided into .Default
}) {}

// scoped — construction acquires resources released with the layer's scope
class Pool extends Effect.Service<Pool>()("App/Pool", {
  scoped: Effect.gen(function* () {
    const pool = yield* Effect.acquireRelease(
      Effect.sync(() => openPool()),
      (p) => Effect.sync(() => p.close())
    )
    return { query: (sql: string) => Effect.sync(() => pool.run(sql)) }
  })
}) {}
declare function openPool(): { run: (sql: string) => unknown; close: () => void }
```

**`.Default` vs `.DefaultWithoutDependencies`:**

- No `dependencies` → only `.Default` exists. Its `RIn` is whatever the `effect`/`scoped` body still requires.
- With `dependencies` → `.DefaultWithoutDependencies` is the raw layer; `.Default` is `DefaultWithoutDependencies` with the dependency layers already `Layer.provide`d. So `Logger.Default` has the `Prefix` requirement *eliminated* — `RIn = never` for that dep.

```ts
import { Layer, Context } from "effect"
Layer.isLayer(Logger.Default)                    // true
Layer.isLayer(Logger.DefaultWithoutDependencies) // true
Context.isTag(Logger)                            // true (the class is the tag)
```

**Accessors (`accessors: true`)** lift each member to a static method on the class so you can skip `yield* Logger` then `.info(...)`:

```ts
// with accessors: true
Logger.info("hello")
//    ^? Effect<void, never, Logger>   — the call site requires Logger
```

**Parameterized layers** — if `effect`/`scoped` is a *function*, `.Default` becomes a function returning a layer:

```ts
class Svc extends Effect.Service<Svc>()("App/Svc", {
  scoped: Effect.fnUntraced(function* (x: number) {
    return { x }
  })
}) {}

Svc.x.pipe(Effect.provide(Svc.Default(42))) // Svc.Default(...) takes the args
```

> `Effect.Service` is marked `@experimental` ("might be up for breaking changes") but is the established, widely-used pattern across the ecosystem.

### `Context.Tag` class pattern

Use when you'd rather hand-author the layer(s), expose several implementations, or keep the service shape in a plain interface:

```ts
import { Context, Effect, Layer } from "effect"

class Random extends Context.Tag("App/Random")<
  Random,
  { readonly next: Effect.Effect<number> }
>() {
  // co-locate layers as statics — a common convention
  static readonly Live = Layer.succeed(this, { next: Effect.sync(() => Math.random()) })
  static readonly Test = Layer.succeed(this, { next: Effect.succeed(0.5) })
}
```

When to still use it:
- You need multiple first-class implementations (`Live`, `Test`, `Mock`) and no single canonical `Default`.
- The service value is a primitive or external object you don't want wrapped in a generated class instance.
- You're publishing a library and want the tag and layers as separate exports (`Context.GenericTag` + standalone `Layer.*`), e.g. platform's `FileSystem` tag.

---

## Accessing services

Inside `Effect.gen`, just `yield*` the tag:

```ts
const program = Effect.gen(function* () {
  const logger = yield* Logger          // get the service
  yield* logger.info("starting")
})
```

In pipe style, the tag *is* an `Effect<Service, never, Id>`, so `flatMap`/`andThen` it:

```ts
import { Effect } from "effect"
const p = Logger.pipe(Effect.flatMap((logger) => logger.info("hi")))
```

### Accessor helpers (derive methods without yielding)

For `Context.Tag`/`GenericTag` services you can derive call-site accessors:

```ts
import { Effect, Context } from "effect"

interface Service {
  foo: (x: string, y: number) => Effect.Effect<string>
  baz: Effect.Effect<string>
}
const Service = Context.GenericTag<Service>("App/Service")

// serviceFunctions — methods that return effects, lifted to standalone fns
const { foo } = Effect.serviceFunctions(Service)
foo("a", 3) //    ^? Effect<string, never, Service>

// serviceConstants — non-function members (and effect-valued members)
const { baz } = Effect.serviceConstants(Service)
baz //    ^? Effect<string, never, Service>

// serviceMembers — both at once
const { functions, constants } = Effect.serviceMembers(Service)
functions.foo("a", 3)
constants.baz

// serviceFunction (singular) — one method
const fooOnly = Effect.serviceFunction(Service, (s) => s.foo)
```

A common idiom is to expose these as statics on the tag class:

```ts
class NumberRepo extends Context.Tag("App/NumberRepo")<
  NumberRepo,
  { readonly numbers: Array<number> }
>() {
  static readonly numbers = Effect.serviceConstants(NumberRepo).numbers
}
```

`Effect.Service`'s `accessors: true` does this automatically; the helpers above are the manual equivalent for `Context.Tag`.

---

## `Layer<ROut, E, RIn>`

A `Layer` is a **recipe for building services**. Read the three type params as:

- `ROut` — the services this layer **produces** (its output context)
- `E` — errors that can occur while *building* it
- `RIn` — the services this layer **needs** to build itself (its inputs / dependencies)

A layer is the constructor; `ROut` is what comes out, `RIn` is what must go in.

### Constructors

```ts
import { Layer, Effect, Context } from "effect"

declare const Tag: Context.Tag<Foo, Foo>; interface Foo { readonly x: number }

Layer.succeed(Tag, { x: 1 })                       // Layer<Foo>            — static value
Layer.sync(Tag, () => ({ x: Date.now() }))         // Layer<Foo>            — lazy value
Layer.effect(Tag, Effect.succeed({ x: 1 }))        // Layer<Foo, E, R>      — from an effect
Layer.scoped(Tag, acquireFoo)                       // Layer<Foo, E, Exclude<R, Scope>> — resourceful
Layer.context<Foo>()                                // Layer<Foo, never, Foo> — pass context through
Layer.fail(new Error("boom"))                       // Layer<unknown, Error>  — build always fails
Layer.die("defect")                                 // Layer<unknown>         — build dies (unchecked)
Layer.effectDiscard(Effect.log("side effect"))      // Layer<never, E, R>     — run for effects only
declare const acquireFoo: Effect.Effect<Foo, never, Scope.Scope>
import type * as Scope from "effect/Scope"
```

- `Layer.scoped` removes `Scope` from `RIn` and ties acquired resources to the layer's lifetime — the canonical way to build connection pools, file handles, servers. (See [Resources & Scope](06-resources-scope.md).)
- `Layer.effectDiscard` / `Layer.scopedDiscard` produce `Layer<never, ...>` — useful for setup that has no service output (e.g. running migrations, setting a FiberRef).
- `Layer.effectContext` / `Layer.succeedContext` / `Layer.scopedContext` build a layer that outputs a whole `Context` (multiple services at once) — see the SQL example below.

### Composition: the dependency-graph mental model

Two axes:

- **Horizontal — `Layer.merge` / `Layer.mergeAll`:** combine sibling layers into one. Outputs union, inputs union, errors union. Use when services are independent peers.
- **Vertical — `Layer.provide`:** feed one layer's outputs into another's *inputs*. `provide(self, deps)` satisfies `self`'s `RIn` from `deps`'s `ROut` and **removes those from the result's `RIn`** (`Exclude<RIn2, ROut>`). The provided services do **not** appear in the output.

```ts
import { Layer } from "effect"

// horizontal — A and B side by side
const AB = Layer.merge(LayerA, LayerB)            // ROut = A | B
const ABC = Layer.mergeAll(LayerA, LayerB, LayerC)

// vertical — Repo needs Database; feed Database in
const RepoWired = RepoLive.pipe(Layer.provide(DatabaseLive))
//   ^? Database is consumed and HIDDEN from output; only Repo is exposed
```

**`Layer.provide` vs `Layer.provideMerge`:**

- `provide(self, deps)` — deps satisfy `self`'s inputs but are **not** re-exposed. Output is just `self`'s `ROut`.
- `provideMerge(self, deps)` — deps satisfy `self`'s inputs **and** stay in the output. Output is `ROut(self) | ROut(deps)`.

```ts
const repoOnly  = RepoLive.pipe(Layer.provide(DatabaseLive))       // ROut = Repo
const repoAndDb = RepoLive.pipe(Layer.provideMerge(DatabaseLive))  // ROut = Repo | Database
```

✅ Do use `provide` for internal plumbing you don't want callers depending on; `provideMerge` when the dependency is also part of your public surface.

Other combinators:

```ts
Layer.map(layer, (ctx) => ctx)            // transform the output Context
Layer.flatMap(layer, (ctx) => otherLayer) // build a layer from this one's output
Layer.flatten(layer, NestedTag)           // flatten a Layer<Layer<...>>
Layer.mapError(layer, (e) => new WrappedError(e))
Layer.orElse(layer, () => fallbackLayer)  // try fallback if build fails
Layer.catchAll(layer, (e) => recoverLayer)
Layer.orDie(layer)                        // turn build errors into defects (E = never)
Layer.retry(layer, schedule)              // retry construction on failure
Layer.tap(layer, (ctx) => Effect.log("built"))
```

### Memoization — the rule that surprises people

> **By default, a layer is built ONCE and shared.** If the same layer reference appears multiple times in a composition graph, its acquisition (and resource allocation) happens a single time and the result is reused everywhere.

This is why a `Config`/`Database` layer feeding many services is constructed only once — not once per consumer.

```ts
// fedB and fedC both depend on the SAME aLayer (which reads ConfigTag).
// aLayer is memoized → built once → both B and C see the FIRST config that wins.
const fedB = bLayer.pipe(Layer.provideMerge(aLayer), Layer.provideMerge(Layer.succeed(ConfigTag, new Config(1))))
const fedC = cLayer.pipe(Layer.provideMerge(aLayer), Layer.provide(Layer.succeed(ConfigTag, new Config(2))))
// In Layer.merge(fedB, fedC): B.value === 1 AND C.value === 1 — aLayer was shared.
```

To opt **out** of sharing, wrap with `Layer.fresh` — it forces a separate build (and separate resource acquisition):

```ts
import { Layer } from "effect"
const env = layer.pipe(Layer.merge(Layer.fresh(layer)))
// acquire runs TWICE: [acquire, acquire, release, release]
```

`Layer.memoize` returns a *scoped effect* yielding a pre-built, shareable layer when you need to control memoization explicitly across separate `Layer.build` calls.

❌ Don't write `Layer.fresh` to "make sure it works" — you'll double-acquire pools/sockets. Sharing is the correct default.
✅ Do rely on memoization: define one `ConfigLive`, reference it from every layer that needs config, compose, and trust it builds once.

---

## Providing layers to effects

```ts
import { Effect, Layer, Context } from "effect"

// provide a whole layer (or an array of layers)
program.pipe(Effect.provide(MainLive))
program.pipe(Effect.provide([Logger.Default, Database.Default]))

// provide a single service value directly (no layer)
program.pipe(Effect.provideService(Random, { next: Effect.succeed(0.5) }))

// provide a service computed by an effect
program.pipe(Effect.provideServiceEffect(Random, makeRandom))
declare const makeRandom: Effect.Effect<{ next: Effect.Effect<number> }>

// provide a raw Context
program.pipe(Effect.provide(Context.make(Random, { next: Effect.succeed(0) })))
```

Each of these subtracts the provided tag(s) from `R` via `Exclude`. `Effect.provide` with multiple layers is the usual app entrypoint.

---

## Full worked example: Config → Database → UserRepo → UserService

Four interdependent services, each an `Effect.Service`, composed into one `MainLive`, provided to a program that runs with `R = never`.

```ts
import { Effect, Layer } from "effect"

// ── 1. Config (leaf — no deps) ───────────────────────────────────────────────
class AppConfig extends Effect.Service<AppConfig>()("App/Config", {
  sync: () => ({
    dbUrl: process.env.DATABASE_URL ?? "postgres://localhost/app",
    logLevel: process.env.LOG_LEVEL ?? "info"
  })
}) {}

// ── 2. Database (depends on Config; owns a resource → scoped) ────────────────
class Database extends Effect.Service<Database>()("App/Database", {
  scoped: Effect.gen(function* () {
    const config = yield* AppConfig
    const conn = yield* Effect.acquireRelease(
      Effect.sync(() => connect(config.dbUrl)),
      (c) => Effect.sync(() => c.close())
    )
    return {
      query: <T>(sql: string) => Effect.sync(() => conn.run(sql) as T)
    }
  }),
  dependencies: [AppConfig.Default]    // Config baked into Database.Default
}) {}

// ── 3. UserRepo (depends on Database) ────────────────────────────────────────
class UserRepo extends Effect.Service<UserRepo>()("App/UserRepo", {
  effect: Effect.gen(function* () {
    const db = yield* Database
    return {
      findById: (id: string) =>
        db.query<{ id: string; name: string }>(`SELECT * FROM users WHERE id = '${id}'`)
    }
  }),
  dependencies: [Database.Default]
}) {}

// ── 4. UserService (depends on UserRepo; exposes accessors) ──────────────────
class UserService extends Effect.Service<UserService>()("App/UserService", {
  accessors: true,
  effect: Effect.gen(function* () {
    const repo = yield* UserRepo
    return {
      greet: (id: string) =>
        Effect.map(repo.findById(id), (u) => `Hello, ${u.name}!`)
    }
  }),
  dependencies: [UserRepo.Default]
}) {}

declare function connect(url: string): { run: (sql: string) => unknown; close: () => void }
```

Because each `.Default` already `Layer.provide`s its own `dependencies`, `UserService.Default` is a fully self-contained layer with `RIn = never`. You can provide just it:

```ts
const program = Effect.gen(function* () {
  return yield* UserService.greet("u_1")   // accessor — requires UserService
})
//    ^? Effect<string, never, UserService>

const runnable = program.pipe(Effect.provide(UserService.Default))
//    ^? Effect<string, never, never>   ← R collapsed to never

Effect.runPromise(runnable)
```

If you'd rather wire the graph explicitly (e.g. to share/swap pieces), build a `MainLive` by hand and provide *without* per-service `dependencies`:

```ts
// Variant: no `dependencies` on the services; compose manually.
// (Imagine each Service defined the same effect but with no `dependencies` array.)
const MainLive = UserService.Default.pipe(
  Layer.provide(UserRepo.Default),
  Layer.provide(Database.Default),
  Layer.provide(AppConfig.Default)
)
//    ^? Layer<UserService, never, never>  — AppConfig is memoized & built once
//       even though Database and (transitively) others reference it.

const runnable2 = program.pipe(Effect.provide(MainLive))
//    ^? Effect<string, never, never>
```

Use `Layer.mergeAll` when you want the entrypoint to expose several top-level services at once:

```ts
const AppLive = Layer.mergeAll(
  UserService.Default,
  Database.Default        // re-exposed too, if other parts of the app need it directly
)
```

---

## Swapping implementations (tests / environments)

Any layer that produces the same tag satisfies the same `R`. Define a `*Test` (or `*Live`) variant and swap it at the provide site — the program under test is unchanged.

```ts
import { Effect, Layer } from "effect"

// A hand-written test layer for the Effect.Service tag:
const UserRepoTest = Layer.succeed(UserRepo, UserRepo.make({
  findById: (_id) => Effect.succeed({ id: _id, name: "Test User" })
}))

const UserServiceTest = UserService.DefaultWithoutDependencies.pipe(
  Layer.provide(UserRepoTest)   // override the real repo with the fake
)

// program runs against the fake — no DB, no config needed
program.pipe(Effect.provide(UserServiceTest))
```

> **`dependencies` seals the graph — swap against `.DefaultWithoutDependencies`.** This is the single easiest way to write a test that silently exercises production. `UserService.Default` *already* has `UserRepo.Default` provided into it, so its `RIn` is `never`:
>
> ```ts
> // ❌ compiles, runs, and quietly uses the REAL repo (and its real DB + config)
> UserService.Default.pipe(Layer.provide(UserRepoTest))
> // ✅ the raw layer still requires UserRepo, so the fake actually lands
> UserService.DefaultWithoutDependencies.pipe(Layer.provide(UserRepoTest))
> ```
>
> `Layer.provide` only satisfies requirements a layer still *has*. Provide something a layer no longer needs and the extra layer is simply built (or memoized) and ignored — no type error, no runtime error, no override. `.DefaultWithoutDependencies` exists precisely for this; it's only generated when the service declares `dependencies`. The alternative is to omit `dependencies` entirely and wire the graph by hand (see the `MainLive` variant above), which keeps every node swappable.

For `Context.Tag` services, co-locate `static Test`/`static Live` layers on the class (shown earlier). For partial fakes that throw on unimplemented methods, use `Layer.mock(tag, partialImpl)` (since 3.17.0):

```ts
import { Layer, Context, Effect } from "effect"

class Mailer extends Context.Tag("App/Mailer")<
  Mailer,
  { send: (to: string) => Effect.Effect<void>; bounce: () => Effect.Effect<void> }
>() {}

const MailerTest = Layer.mock(Mailer, {
  send: () => Effect.void      // bounce() left out → defect if ever called
})
```

Deeper testing patterns (TestClock, layer-scoped fixtures, `it.layer`) live in [Testing](15-testing.md).

---

## Config integration (brief)

Services frequently read configuration during construction. Build them with `Layer.effect`/`Layer.scoped` and `yield*` a `Config`, or unwrap a `Config.Config.Wrap` into a scoped context. Real-world shape (from `@effect/sql-pg`):

```ts
import { Config, Effect, Layer, Context } from "effect"

// service constructor reads typed config; layer fails with ConfigError if missing
const layerConfig = (config: Config.Config.Wrap<{ host: string; port: number }>) =>
  Layer.scopedContext(
    Config.unwrap(config).pipe(
      Effect.flatMap((c) => makeClient(c)),
      Effect.map((client) => Context.make(SqlClient, client))
    )
  )
declare const SqlClient: Context.Tag<unknown, unknown>
declare function makeClient(c: { host: string; port: number }): Effect.Effect<unknown>
```

The resulting layer's `E` includes `ConfigError`, and the program surfaces missing/invalid config as a typed failure at build time. For `Config` schemas, validation, and providers, see the schema/config reference.

---

## Cheat sheet

| Goal | API |
| --- | --- |
| Declare requirement + impl + layer in one | `class X extends Effect.Service<X>()("App/X", { effect / scoped / sync / succeed, dependencies?, accessors? }) {}` |
| Auto layer with deps wired | `X.Default` (raw: `X.DefaultWithoutDependencies`) |
| Tag-only service | `class X extends Context.Tag("App/X")<X, Shape>() {}` |
| Read a service | `yield* X` · `X.pipe(Effect.flatMap(...))` · `Effect.serviceFunctions/Constants/Members(X)` |
| Build a layer | `Layer.succeed/sync/effect/scoped/context/fail/die/effectDiscard` |
| Combine peers | `Layer.merge` · `Layer.mergeAll` |
| Feed dependencies | `Layer.provide` (hide) · `Layer.provideMerge` (hide + re-expose) |
| Force a fresh build | `Layer.fresh` (default is shared/memoized) |
| Provide to an effect | `Effect.provide(layer)` · `Effect.provideService(Tag, v)` · `Effect.provideServiceEffect(Tag, eff)` |
| Swap for tests | another layer producing the same tag · `Layer.mock(tag, partial)` |

---

## See also

- [Mental model](01-mental-model.md) — what the `A / E / R` channels mean
- [Resources & Scope](06-resources-scope.md) — `Layer.scoped`, `acquireRelease`, resource lifetimes
- [Testing](15-testing.md) — providing test layers, `it.layer`, TestClock
- Schema & Config reference — typed configuration that feeds layers
