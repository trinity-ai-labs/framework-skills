<!-- verified: effect@4.0.0 -->
# Architecture: laying out an Effect 4 codebase

> **When you reach for this:** before you write the second service. This chapter is about structure: where services, layers, errors, the program's edge and the unstable modules go, and what Effect 4 changes about each. It does not teach the APIs. The installed package's `AGENTS.md` and `ai-docs/` do that, and this chapter names the example to open instead of repeating it.

The argument is the one that held in v3. Code is good when it is easy to change. `Effect<A, E, R>` makes a function's dependencies, failures and effects visible in its type, which lets you build modules that hide a lot behind a small interface and have the compiler check the boundary. What v4 changes is the machinery around that argument: one service constructor, no generated layers, fewer packages, an unstable tier you have to place somewhere, and layer memoization that now crosses `Effect.provide` calls.

The examples use "the reference app": a small user service over SQL. Paths beginning `ai-docs/` are inside the installed `effect` package. The `migration/*.md` guides this chapter cites are not shipped in it: they are in the `Effect-TS/effect` repository at the `effect@4.0.0` tag.

## Contents

- [A service is a deep module](#a-service-is-a-deep-module)
- [The layer graph is the architecture](#the-layer-graph-is-the-architecture)
- [Layer memoization changes how the graph is assembled](#layer-memoization-changes-how-the-graph-is-assembled)
- [Run at the edge, describe everywhere else](#run-at-the-edge-describe-everywhere-else)
- [Errors are domain vocabulary](#errors-are-domain-vocabulary)
- [How to lay out files](#how-to-lay-out-files)
- [Where unstable modules sit](#where-unstable-modules-sit)
- [Keep Effect at the core, adapt at the boundaries](#keep-effect-at-the-core-adapt-at-the-boundaries)
- [Project setup](#project-setup)
- [Testing falls out of the architecture](#testing-falls-out-of-the-architecture)
- [Habits that keep the codebase changeable](#habits-that-keep-the-codebase-changeable)
- [See also](#see-also)

---

## A service is a deep module

A deep module hides a lot of behaviour behind a small interface. In Effect that is a service: the interface is the contract callers see, the layer is the implementation, and the `R` channel makes every dependency edge compiler-checked.

In v4 the one way to define a service is `Context.Service`. The bundled guide (`AGENTS.md`, "Writing Effect services") shows the class form, and `ai-docs/src/01_effect/03_services/01_service.ts` is the runnable version. This is the reference app's repository, written the way the guide writes it:

```ts
// src/services/UserRepo.ts
import { Context, Effect, Layer, Schema } from "effect"
import { EmailAlreadyTaken, User, UserId, UserNotFound } from "../domain/User.ts"
import { Db } from "../infra/Db.ts"

export class UserRepo extends Context.Service<UserRepo, {
  findById(id: UserId): Effect.Effect<User, UserNotFound>
  create(input: { readonly name: string; readonly email: string }): Effect.Effect<User, EmailAlreadyTaken>
}>()("app/services/UserRepo") {
  // The layer states what it needs in its type: Layer<UserRepo, never, Db>.
  static readonly layer = Layer.effect(
    UserRepo,
    Effect.gen(function*() {
      const db = yield* Db

      const findById = Effect.fn("UserRepo.findById")(function*(id: UserId) {
        const rows = yield* db.query("SELECT id, name, email FROM users WHERE id = ?", [id]).pipe(Effect.orDie)
        const row = rows[0]
        if (row === undefined) return yield* new UserNotFound({ id })
        return yield* Schema.decodeUnknownEffect(User)(row).pipe(Effect.orDie)
      })

      const create = Effect.fn("UserRepo.create")(function*(input: { readonly name: string; readonly email: string }) {
        const taken = yield* db.query("SELECT 1 FROM users WHERE email = ?", [input.email]).pipe(Effect.orDie)
        if (taken.length > 0) return yield* new EmailAlreadyTaken({ email: input.email })
        const id = UserId.make(crypto.randomUUID())
        yield* db.query("INSERT INTO users (id, name, email) VALUES (?, ?, ?)", [id, input.name, input.email]).pipe(Effect.orDie)
        return new User({ id, ...input })
      })

      return UserRepo.of({ findById, create })
    })
  )
}
```

What this chapter adds is the judgment around that shape.

**Design the interface, delegate the body.** You own the methods, their domain types and their errors. What sits behind them can be written faster and reviewed less closely, because the boundary is type-checked and testable. The interface above lists two domain errors and nothing else: a database failure is not something a caller of `findById` can act on, so the body turns it into a defect with `Effect.orDie`. The SQL example in the package (`ai-docs/src/40_sql/10_basics.ts`) makes the same call. Keep infrastructure errors out of the interface unless a caller has a real recovery for them.

**There is no generated layer, so you write one and you name it.** v3's service helper (`Service` on the `Effect` module) generated a `Default` layer and wired a `dependencies` option into it. 4.0.0 has neither: `Context.Service` takes an optional `make` effect, and you build the layer yourself with `Layer.effect` (upstream's `migration/services.md` has the before and after). Pick one naming rule for the codebase. The bundled examples use `layer` for the primary layer and suffixes for variants (`layerTest`, `layerConfig`, `layerNoDeps`). In `ai-docs/.../20_layer-composition.ts`, `layerNoDeps` is the layer with its requirements left open and `layer` is that layer with the concrete dependency provided. This chapter's convention is the opposite split, and the reason is the next section: services leave their requirements open, and `App.ts` is the only file that provides them. Either convention works. A codebase that uses both does not.

**Access the service with `yield*`, not `use`.** `Context.Service` classes have a `use` accessor, and the migration guide itself says to prefer `yield*`: `use` hides the dependency inside a callback, so the `R` channel is the only place it shows up and a service can leak into return values. Reach for `use` for one-liners at an edge (the Hono example in `ai-docs/src/04_integration/10_managed-runtime.ts` does), not in service bodies.

❌ Don't expose a dozen loosely related functions that each take a `db` and a `logger`: the wiring leaks into every caller.
✅ Do collect them behind one service and hide the dependencies in its layer.

---

## The layer graph is the architecture

The wiring of an Effect program is a typed value: the composition of its layers. The shape of that graph is the architecture, and the compiler checks that it is complete.

```text
                 Db                (scoped: owns the connection)
                  │
                  ▼
              UserRepo
                  │
                  ▼
             UserService
```

Each edge is a `Layer.provide`. One file assembles them. The two combinators that matter are in `ai-docs/.../20_layer-composition.ts`: `Layer.provide` feeds a layer's requirements and exposes only the layer itself, `Layer.provideMerge` feeds them and keeps the provided services in the output too. Reach for `provideMerge` when something above the graph (a migrator, a test) needs the lower service as well.

```ts
// src/services/UserService.ts
import { Context, Effect, Layer } from "effect"
import { UserId } from "../domain/User.ts"
import type { UserNotFound } from "../domain/User.ts"
import { UserRepo } from "./UserRepo.ts"

export class UserService extends Context.Service<UserService, {
  greet(id: UserId): Effect.Effect<string, UserNotFound>
}>()("app/services/UserService") {
  static readonly layer = Layer.effect(
    UserService,
    Effect.gen(function*() {
      const repo = yield* UserRepo
      const greet = Effect.fn("UserService.greet")(function*(id: UserId) {
        const user = yield* repo.findById(id)
        return `Hello, ${user.name}!`
      })
      return UserService.of({ greet })
    })
  )
}
```

```ts
// src/App.ts: the only file that knows the whole graph
import { Layer } from "effect"
import { Db } from "./infra/Db.ts"
import { UserRepo } from "./services/UserRepo.ts"
import { UserService } from "./services/UserService.ts"

export const AppLayer = UserService.layer.pipe(
  Layer.provide(UserRepo.layer),
  Layer.provide(Db.layerSqlite("app.db"))
)
// Layer<UserService, never, never>: nothing left to provide
```

What falls out of it: one place to read what the application depends on; a `RIn` of `never` as the "fully wired" check; and a swap point at every node. A different layer for the same service replaces the whole subtree above it, which is the test seam, the dev-versus-production seam and the in-memory-versus-database seam at once.

`App.ts` is a file in the layout below, not a convention you have to remember, because services leave their requirements open. A service whose `layer` quietly provides its own concrete dependencies is easier to launch alone, but it imports the implementation of its neighbour, hides that edge from the graph, and needs a second, open variant for every test. Use the wired form for a leaf that has exactly one possible dependency (a config service, say), not as the default.

### Layer memoization changes how the graph is assembled

In v3 each `Effect.provide` call had its own memoization scope, so two provides of overlapping layers silently built the shared layer twice. In v4 the memo map is shared between `Effect.provide` calls (upstream's `migration/layer-memoization.md`). Upstream's own advice is that composing before providing is still the pattern, and the sharing is "a safety net". The programs below were run against 4.0.0 to find out exactly what the safety net covers, because the guide's wording is looser than the behaviour:

```ts
// src/memo.ts
import { Console, Context, Effect, Layer } from "effect"

class Db extends Context.Service<Db, { readonly url: string }>()("app/Db") {
  static readonly layer = Layer.effect(
    Db,
    Effect.acquireRelease(
      Console.log("db: acquire").pipe(Effect.as({ url: "app.db" })),
      () => Console.log("db: release")
    )
  )
}

// Two services that each wire their own copy of the same Db layer.
class Users extends Context.Service<Users, object>()("app/Users") {
  static readonly layer = Layer.effect(Users, Effect.gen(function*() {
    yield* Db
    yield* Console.log("users: build")
    return {}
  })).pipe(Layer.provide(Db.layer))
}

class Orders extends Context.Service<Orders, object>()("app/Orders") {
  static readonly layer = Layer.effect(Orders, Effect.gen(function*() {
    yield* Db
    yield* Console.log("orders: build")
    return {}
  })).pipe(Layer.provide(Db.layer))
}

const program = Effect.gen(function*() {
  yield* Users
  yield* Orders
  yield* Console.log("run")
})

// Nested provides: Db is built once, and released after "run".
export const nested = program.pipe(
  Effect.provide(Users.layer),
  Effect.provide(Orders.layer)
)

// Sibling provides: each one builds, and releases, its own Db.
export const siblings = Effect.all([
  Effect.void.pipe(Effect.provide(Db.layer)),
  Effect.void.pipe(Effect.provide(Db.layer))
])
```

Running `nested` prints `db: acquire`, `orders: build`, `users: build`, `run`, `db: release`: one acquire. Running `siblings` prints `db: acquire`, `db: release`, `db: acquire`, `db: release`. Measured on 4.0.0, with the same `Db.layer` value throughout:

| Arrangement | Db built |
| --- | --- |
| Nested provides (a `pipe` of two `Effect.provide`s) | once |
| Sibling provides (two separate effects, each provided) | once per sibling |
| `Effect.provide(layer, { local: true })` on the **inner** provide | twice |
| `{ local: true }` on the **outer** provide, with plain provides inside it | once: everything provided beneath a local provide shares that provide's own map |
| `Layer.fresh(layer)` on one of them | twice |
| Two layer values for the same service, from calling a factory twice | twice |
| Two `ManagedRuntime.make` calls, default options | once per runtime |
| Two `ManagedRuntime.make` calls given one `memoMap` | once, released when the last runtime is disposed |

Upstream's guide comments that `{ local: true }` on the second provide in a pipe builds twice. In the order measured here (the local provide outermost) it built once, because a plain provide builds its layer in a map forked from the one the fiber already carries and passes that map down to every provide inside it, while `{ local: true }` starts from a fresh, unrelated map that the provides inside it then fork from. Sharing flows inward, from an outer provide to the ones nested beneath it, and it is keyed on the layer value, not on the service it provides. Trust a run over the comment, and run it again after an upgrade (see [Stability](02-stability.md)).

What this changes about where code goes:

- **Layers that carry their own dependencies stop being a double-build hazard.** The v3 reason to hoist every `Layer.provide` into one file was partly to get one pool. That reason is weaker. It is not gone: the graph in one file is still the readable form, and sibling provides still do not share.
- **Define each layer once, as a module-level value.** Sharing is by identity. A function that returns a new layer on every call (`Db.layerSqlite("app.db")` called from two places) gives two layers and two pools. Bind the configured layer to a constant and import that.
- **Provide once, at the edge.** Several `Effect.provide` calls scattered through the code now mostly behave when they are nested and mostly do not when they are siblings, which is harder to reason about than a single provide of `AppLayer`.
- **Isolate on purpose.** Where a test, a tenant or a worker needs its own copy of a resource, say so with `{ local: true }` (the whole subtree is private) or `Layer.fresh` (that one layer). Do not rely on the layer happening to be built separately.
- **A host with more than one runtime shares one memo map.** See the next section.

---

## Run at the edge, describe everywhere else

An Effect program is a description. There should be exactly one place per entry point where the description meets the running world.

```ts
// src/main.ts: the one place we run
import { NodeRuntime } from "@effect/platform-node"
import { Console, Effect } from "effect"
import { UserId } from "./domain/User.ts"
import { AppLayer } from "./App.ts"
import { UserService } from "./services/UserService.ts"

const program = Effect.gen(function*() {
  const users = yield* UserService
  yield* Console.log(yield* users.greet(UserId.make("u1")))
})

program.pipe(
  Effect.provide(AppLayer),
  NodeRuntime.runMain
)
```

Three entry shapes cover most programs:

- **A job or a CLI:** `NodeRuntime.runMain` (the Node runner lives in `@effect/platform-node`, the Bun one in `@effect/platform-bun`). `ai-docs/src/01_effect/06_running/10_run-main.ts`.
- **A server or a worker, where the whole application is layers:** build one layer that does the work, turn it into the entry effect with `Layer.launch`, and run that with `runMain`. A long-running fiber is a scoped layer too (`Layer.effectDiscard` with `Effect.forkScoped`, in `ai-docs/src/01_effect/05_resources/20_layer-side-effects.ts`), so closing the scope interrupts it. The HTTP server, the background workers and the metrics exporter are all layers. `ai-docs/src/01_effect/06_running/20_layer-launch.ts`.
- **A host you do not control** (a web framework, a test runner, a serverless handler): build one `ManagedRuntime` from `AppLayer` and run effects through it. `ai-docs/src/04_integration/10_managed-runtime.ts`.

```ts
// src/runtime.ts
import { Layer, ManagedRuntime } from "effect"
import { AppLayer } from "./App.ts"

// One memo map for the process, so several runtimes share layers like Db
// instead of each building its own.
const memoMap = Layer.makeMemoMapUnsafe()

export const runtime = ManagedRuntime.make(AppLayer, { memoMap })

// On shutdown: await runtime.dispose()
```

**A long-lived program goes through `runMain`.** It is what listens for `SIGINT` and `SIGTERM` and interrupts the root fiber (so scoped layers release), sets the exit code and reports unhandled errors. On 4.0.0 a program that only waits exits unless it runs under `runMain`; see [Pitfalls](04-pitfalls.md) item 17 for the measurements. Do not replace it with `runPromise` in a service that is meant to stay up.

The corollary for the rest of the code is the v3 one. `Effect.runPromise` and `Effect.runSync` inside business logic discard the surrounding context, interruption and tracing. And there is no `Runtime<R>` value to pass around any more: in v4 that type is gone (upstream's `migration/runtime.md`). If a callback needs to run an effect with the current services, capture them with `Effect.context` and run with `Effect.runForkWith`; if a host needs to run many effects, give it a `ManagedRuntime`.

❌ Don't call `Effect.runPromise` from a service and `await` it.
✅ Do thread the effect up and run it once, at the entry point, with `runMain` (around `Layer.launch` for a layer-shaped application) or a `ManagedRuntime`.

---

## Errors are domain vocabulary

The `E` channel is where the domain's failure modes become named, typed values. Treat the error names as part of the ubiquitous language of the codebase: a signature such as `Effect<Receipt, PaymentDeclined | OutOfStock, PaymentGateway>` reads as a specification.

Which base class: the bundled `AGENTS.md` defines every error with `Schema.TaggedError`, and so do all its `ai-docs` examples. `Data.TaggedError` still exists in 4.0.0, but follow the guide. The practical reason is that a `Schema` error carries a schema, so the `HttpApi` fixtures in the package declare their endpoint errors with the same classes the services fail with (`ai-docs/src/51_http-server/fixtures/domain/UserErrors.ts`). Keep the errors in the domain layer, with no I/O:

```ts
// src/domain/User.ts
import { Schema } from "effect"

export const UserId = Schema.String.pipe(Schema.brand("UserId"))
export type UserId = typeof UserId.Type

export class User extends Schema.Class<User>("User")({
  id: UserId,
  name: Schema.String,
  email: Schema.String
}) {}

export class UserNotFound extends Schema.TaggedError<UserNotFound>()("UserNotFound", {
  id: UserId
}) {}

export class EmailAlreadyTaken extends Schema.TaggedError<EmailAlreadyTaken>()("EmailAlreadyTaken", {
  email: Schema.String
}) {}
```

**One error per service, with a `reason`, when the failure modes are many.** A service that can fail in a dozen ways does not need a dozen entries in every signature above it. v4 adds first-class support for a tagged error whose `reason` field is a union of tagged errors, with `Effect.catchReason`, `Effect.catchReasons` and `Effect.unwrapReason` to recover. The example is `ai-docs/src/01_effect/04_errors/20_reason-errors.ts`, and the server fixtures in `ai-docs/src/51_http-server/fixtures/` show the edge using it to map a repository's reasons onto HTTP outcomes.

```ts
import { Effect, Schema } from "effect"

export class CardDeclined extends Schema.TaggedError<CardDeclined>()("CardDeclined", {
  code: Schema.String
}) {}

export class GatewayUnavailable extends Schema.TaggedError<GatewayUnavailable>()("GatewayUnavailable", {}) {}

// The one error callers of the payment service see.
export class PaymentError extends Schema.TaggedError<PaymentError>()("PaymentError", {
  reason: Schema.Union([CardDeclined, GatewayUnavailable])
}) {}

declare const charge: Effect.Effect<string, PaymentError>

// At the edge: retry-worthy reasons are handled, the rest stay in the channel.
export const chargeOrWait = charge.pipe(
  Effect.catchReason("PaymentError", "GatewayUnavailable", () => Effect.succeed("queued"))
)
```

**Typed `E` is for outcomes callers can act on; everything else is a defect.** `Effect.orDie` at a service boundary (as in `UserRepo` above) is how an infrastructure failure becomes one. A defect crashes loudly and shows up in logs and traces. Do not model "this should never happen" in the error channel. The diagnosis of a messy error channel (leaked infrastructure errors, `unknown` creeping in) is in [Pitfalls](04-pitfalls.md).

❌ Don't fail with `Error` and a message string: `catch (e: unknown)` is back and the signature says nothing.
✅ Do name each recoverable failure in domain terms and let unexpected failures be defects.

---

## How to lay out files

One module per file, with the contract, its implementation and its errors together. A service file is a deep module and the file is its boundary.

```text
src/
  domain/            types, schemas, branded ids, tagged errors. No I/O. Stable imports only.
    User.ts
  services/          one deep module per file: the service class and its layer(s)
    UserRepo.ts
    UserService.ts
  infra/             the only importers of third-party-backed and unstable modules, outbound
    Db.ts
  edge/              the only importers of unstable modules inbound: HTTP, CLI, RPC
    api.ts           the HttpApi definition
    handlers.ts      handler groups: decode, call a service, encode. No business logic.
  App.ts             AppLayer: the layer graph, assembled once
  main.ts            the entry point: provide AppLayer, runMain
```

- **`domain/` depends on nothing in the app.** It is the vocabulary everything else speaks.
- **A service file exports its class and its layers.** The class is the interface; the layer is private detail that happens to be exported for `App.ts` and tests.
- **The edge is thin.** Handlers translate between the outside world and services. The package's HttpApi example keeps the API definition apart from the server implementation on purpose, so a client can import the definition without pulling in server code (`ai-docs/src/51_http-server/10_basics.ts`, with fixtures under `fixtures/api` and `fixtures/server`).
- **`App.ts` is the only file that knows the whole graph.** Keep wiring out of leaf modules.

For a larger application group by feature first and by role inside it (`users/`, `billing/`, each with its own `domain.ts`, services and edge file, and a `UsersLayer` that `App.ts` composes), with the shared infrastructure in `shared/`. A feature exposes a few services and a layer, which keeps each bounded context a deep module of its own. Whether `infra/` and `edge/` sit at the top or inside each feature is a choice about team boundaries and does not change the rule that follows.

---

## Where unstable modules sit

In v4 the stability of an export is not visible in its import path. Most of what an application builds on beyond the core modules is tagged `unstable` and may break in a minor release: `effect/http`, `effect/http-api`, `effect/sql`, `effect/rpc`, `effect/cli`, `effect/schema` and others (the exact tier of any export comes from `stability.mjs`, never from this list, and the discipline of pinning and checking is in [Stability](02-stability.md)). A stable module can also hold an unstable export, and so can an export that exposes a third-party dependency. This chapter's question is a structural one: where in the layout do those imports live?

**The rule: unstable imports live in a small number of directories, and the stable core does not import from them.** In the layout above that is `infra/` for outbound dependencies and `edge/` for inbound ones. Name the directories after the role and not after the tier: the tier belongs to an export, it changes between releases, and a directory called `unstable/` would be wrong the day an export is promoted.

**Outbound: wrap it in a service you own.** The database client is the typical case. `effect/sql` is unstable, so one module is its only importer, and it exposes a service whose interface is yours:

```ts
// src/infra/Db.ts: the only file that imports effect/sql and the driver
import { SqliteClient } from "@effect/sql-sqlite-node"
import { Context, Effect, Layer, Schema } from "effect"
import { SqlClient } from "effect/sql"

export class DbError extends Schema.TaggedError<DbError>()("DbError", {
  cause: Schema.Defect()
}) {}

export class Db extends Context.Service<Db, {
  query(
    text: string,
    params?: ReadonlyArray<unknown>
  ): Effect.Effect<ReadonlyArray<Record<string, unknown>>, DbError>
}>()("app/infra/Db") {
  static readonly layer = Layer.effect(
    Db,
    Effect.gen(function*() {
      const sql = yield* SqlClient.SqlClient
      const query = Effect.fn("Db.query")((text: string, params?: ReadonlyArray<unknown>) =>
        sql.unsafe<Record<string, unknown>>(text, params).pipe(
          Effect.mapError((cause) => new DbError({ cause }))
        )
      )
      return Db.of({ query })
    })
  )

  // The driver is part of the boundary: callers never see SqlClient in R.
  static readonly layerSqlite = (filename: string) =>
    this.layer.pipe(
      Layer.provide(SqliteClient.layer({ filename }))
    )
}
```

When `effect/sql` changes in a minor release, this file is the diff. The rest of the application sees `Db`, `DbError` and the types it declared. Three leaks are worth checking for in review, because each carries an unstable type across the boundary without an import: the error channel (`SqlError` in a service's `E`), the requirements (`SqlClient` in a layer's `RIn`) and a parameter or return type taken from the module. The wrapper above converts the first with `mapError`, `layerSqlite` hides the second by providing the driver, and uses only plain types for the third. A wrapper that merely re-exports the unstable module is a barrel and protects nothing.

**Do not wrap more than you use.** A wrapper that mirrors the whole unstable API is a second API to maintain. Expose the handful of operations the application calls, in the application's terms.

**Inbound: confine the framework to the edge.** An `HttpApi` definition, a CLI command tree or an RPC group is the edge by nature, and hiding it behind an interface would only be indirection. Put it in `edge/` and let it call into services. Keep the unstable surface out of what the services return: handlers decode a request into domain types, call a service, and encode the result, and no service signature mentions `HttpServerRequest` or an endpoint type.

**Keep unstable modules out of `domain/`.** The place it creeps in is `Model.Class` from the lowercase `effect/schema` group (not the `effect/Schema` module): the SQL example uses it, it is unstable, and `Schema.Class` from `effect/Schema` is stable. If a persistence model is worth having, define it in `infra/` and map it to the domain class, so a domain type never depends on a version-sensitive module.

**Make the rule checkable.** A lint rule restricting imports (ESLint's `no-restricted-imports` does this) that bans the unstable specifiers outside `infra/` and `edge/` turns the layout into something a reviewer does not have to hold in their head, and an upgrade's blast radius is then a list of two directories. Write the allowed specifiers down once. The list lives in the lint config, and `stability.mjs` is how you decide what belongs on it.

The cost is real: one more file per dependency, and a mapping where an error or a type crosses. Pay it for dependencies the application cannot live without and that are unstable. Do not pay it for a stable module such as `effect/Schema` or `effect/Config`.

---

## Keep Effect at the core, adapt at the boundaries

Domain code and services should be Effect all the way down, because that is where typed errors, context and interruption pay off. Where the non-Effect world appears, wrap it once:

| Boundary | Adapt with |
| --- | --- |
| A promise-returning SDK | `Effect.tryPromise`, and name the failure |
| A callback or an event emitter | `Effect.callback` |
| Untrusted input (HTTP body, file, message) | `Schema.decodeUnknownEffect` into a typed value or a `SchemaError` |
| Configuration and secrets | `Config` with `Config.Redacted`, provided through a layer (`20_layer-composition.ts` in the services examples uses `Config.Redacted`; `20_layer-unwrap.ts` builds a layer from configuration) |
| An `Option` or a `Result` you hold | `Effect.fromOption` and `Effect.fromResult`; neither is yieldable in `Effect.gen` on 4.0.0, whatever `migration/yieldable.md` says |
| A UI framework or a web handler | a `ManagedRuntime`; the framework-specific atom bindings (`@effect/atom-*`) where they exist |
| Time and randomness | `Clock`, `Effect.sleep`, `DateTime.now`, `Random`; never `Date.now` or `Math.random`, so `TestClock` can drive the code |

```ts
import { Effect, Option, Schema } from "effect"

class UpstreamError extends Schema.TaggedError<UpstreamError>()("UpstreamError", {
  cause: Schema.Defect()
}) {}

// A promise API: the thrown value becomes a named failure.
export const fetchText = (url: string) =>
  Effect.tryPromise({
    try: (signal) => fetch(url, { signal }).then((r) => r.text()),
    catch: (cause) => new UpstreamError({ cause })
  })

// A callback API: resume once, return a cleanup effect.
export const nextTick = Effect.callback<void>((resume) => {
  const handle = setTimeout(() => resume(Effect.void), 0)
  return Effect.sync(() => clearTimeout(handle))
})

// An Option is not an Effect: convert it where you need one.
export const required = (value: string | undefined) => Effect.fromOption(Option.fromNullishOr(value))
```

Wrapping at the edge keeps the inside composable and the messy parts in small adapters.

### Adopting Effect in an existing codebase

Adopt it inward-out; a half-converted codebase is a legitimate place to rest. Pick one leaf with real pain (retries, timeouts, flaky I/O). Give it a service interface, wrap the existing implementation behind it and name its failures. Keep one runtime for the process: build a single `ManagedRuntime` and reuse it, never run a freshly built layer graph per call, or every call re-acquires its resources. As callers convert, delete their run call and let them `yield*`, so the edge moves up the call tree. Convert along one vertical slice at a time (one request path, one job) so every step ships, and convert the error handling before the convenience code, since the benefit is concentrated in the `E` channel.

---

## Project setup

- **`strict: true`.** Effect's inference leans on strict null checks and variance. Upstream's own base configuration (`tsconfig.base.json` at the `effect@4.0.0` tag) also sets `target` `ES2022`, `module` `NodeNext`, `verbatimModuleSyntax`, `exactOptionalPropertyTypes`, `noUnusedLocals` and `noImplicitOverride`. Those are the settings the library is built with, a good default for a new project and not a requirement for using it. The `ai-docs` examples import with `.ts` extensions (`from "../domain/User.ts"`), which upstream supports with `rewriteRelativeImportExtensions`.
- **ESM.** The package is `"type": "module"` and reaches its modules through an `exports` map (`effect/Effect`, `effect/http`, and so on), which `moduleResolution` `NodeNext` resolves.
- **`@effect/language-service`.** The editor plugin still exists (0.87.3 on npm when this was verified) and its diagnostics list a v4 column, including an `outdatedApi` check for APIs removed or renamed in v4. Add it under `compilerOptions.plugins` as `{ "name": "@effect/language-service" }`, and select the workspace TypeScript in your editor. Upstream's README says that on TypeScript 7 or newer you use `@effect/tsgo` instead.
- **Packages a typical application installs.** `effect` carries the core and the consolidated former packages: `effect/http`, `effect/http-api`, `effect/rpc`, `effect/sql`, `effect/cluster` and `effect/cli` are subpaths of it. What stays separate and are released on the same version number as `effect` (so `effect@4.0.0` goes with `@effect/platform-node@4.0.0`), and upstream's migration guide says to bump them together:
  - `@effect/platform-node` (or `@effect/platform-bun`): `runMain` and the HTTP server and client backends.
  - a driver such as `@effect/sql-sqlite-node` or `@effect/sql-pg`.
  - `@effect/vitest` for tests, which has `vitest` as a peer dependency (its range was `>=5.0.0 <6.0.0` when this was verified).
  - `@effect/opentelemetry` if you integrate with an existing OpenTelemetry setup. For new projects the bundled guide recommends the `Otlp` modules in `effect/observability`.
- **One copy of `effect`.** The platform and driver packages peer-depend on `effect ^4.0.0`. Two copies produce service identities that do not match, and the symptom is a service that "won't provide". The language service has a `duplicatePackage` diagnostic for this.
- **Let an agent read the guide.** `node_modules/effect/AGENTS.md` is written for a coding agent working in your project. Point your own agent guidance at it, and install `effect` at the repository root of a monorepo so the path is stable.

---

## Testing falls out of the architecture

Deep modules with layer boundaries are the testability. To test `UserService`, give it a fake `UserRepo` and leave the service alone. Because services leave their requirements open, the service's own `layer` is the unit under test:

```ts
// src/services/UserService.test.ts
import { assert, it } from "@effect/vitest"
import { Effect, Layer } from "effect"
import { User, UserId, UserNotFound } from "../domain/User.ts"
import { UserRepo } from "./UserRepo.ts"
import { UserService } from "./UserService.ts"

const UserRepoTest = Layer.succeed(
  UserRepo,
  UserRepo.of({
    findById: (id) =>
      id === "u1"
        ? Effect.succeed(new User({ id, name: "Test", email: "t@example.com" }))
        : Effect.fail(new UserNotFound({ id })),
    create: (input) => Effect.succeed(new User({ id: UserId.make("new"), ...input }))
  })
)

const TestLayer = UserService.layer.pipe(Layer.provide(UserRepoTest))

it.effect("greets the user", () =>
  Effect.gen(function*() {
    const users = yield* UserService
    assert.strictEqual(yield* users.greet(UserId.make("u1")), "Hello, Test!")
  }).pipe(Effect.provide(TestLayer)))
```

Two v4 facts bear on how tests share state. `layer(...)` from `@effect/vitest` builds one layer for a whole `describe` block and tears it down afterwards, so state persists from one test to the next (the second test in `ai-docs/src/09_testing/20_layer-tests.ts` depends on exactly that). That is the right default for an expensive resource and the wrong one for mutable fake state. For isolation, provide the layer inside each test, with `{ local: true }` or `Layer.fresh` if the layer might otherwise be found in a map shared with an outer provide (see the memoization section). `TestClock` is in `effect/testing`, and time-dependent code (retries, timeouts, schedules) runs instantly under it because the code used `Effect.sleep` and not real timers.

If something is hard to test, the boundary is in the wrong place. That is design feedback, so act on it.

---

## Habits that keep the codebase changeable

- **Invest in the design on every change.** Each change either improves the module boundaries or erodes them. When a service interface starts collecting unrelated methods, split it.
- **Name things in the domain's language.** Services, methods, errors, branded ids. Precise, consistent names are also what make the codebase legible to an agent.
- **Prefer fewer, deeper services** over many shallow ones. A `Billing` service with a focused interface beats `chargeCard`, `refund` and `getInvoice` scattered as free functions sharing five dependencies.
- **Make a dependency explicit, then hide it.** If a function reaches for a global, give it a service. If a service's internals leak into callers, tighten the interface.
- **Let `R = never` be the "fully wired" check** at the entry point.
- **Wrap an unstable module the day you import it,** not the day it breaks. Adding the wrapper later means finding every importer.
- **Re-run the memoization table after an upgrade** if your assembly depends on it. It describes 4.0.0 and the guide that shipped with it is looser than the code.
- **Keep comments scarce.** Clear names and types over prose; comment only logic that is not obvious.

---

## See also

- [Coming from v3](01-coming-from-v3.md): what a v3 habit gets wrong in v4, including the removal of v3's `Service` helper and Tag classes
- [Stability](02-stability.md): the tiers, how to look one up, pinning, and the discipline behind the boundary in this chapter
- [Pitfalls](04-pitfalls.md): recurring mistakes and diagnosing a messy `E` or `R` channel
- The installed package: `AGENTS.md`, and `ai-docs/src/01_effect/03_services/`, `04_errors/`, `06_running/`, `09_testing/`
- Upstream's migration guides for the mechanisms touched here: `services.md`, `layer-memoization.md`, `fiber-keep-alive.md`, `runtime.md`
