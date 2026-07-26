# Architecture: organizing Effect programs

> **When you reach for this:** before you write the second service. This file is about *structure* — how to lay out an Effect codebase so it stays easy to change, easy to test, and easy for both you and an AI to navigate. The other files teach the parts; this one teaches how to assemble them.

The thesis (borrowed from Ousterhout's *A Philosophy of Software Design*, Brooks, and Kent Beck): **bad code is code that is hard to change.** Effect's value is not "functional programming points" — it's that `Effect<A, E, R>` makes dependencies, errors, and effects *explicit and type-checked*, which lets you build **deep modules with simple interfaces** and verify them at the boundary. Lean into that or you get none of the benefit.

---

## The core idea: a service is a deep module

> **Deep module** (Ousterhout): a lot of functionality hidden behind a *simple interface*. Shallow modules — many tiny pieces with wide interfaces — are what make a codebase hard to navigate and hard for an AI to reason about.

Effect gives you a first-class deep-module primitive:

- The **`Tag` + service interface** is the *simple interface* — a small, named contract (`UserRepo` has `findById`, `create`).
- The **`Layer`** is the *deep implementation* — connection pools, retries, caching, SQL, all hidden behind that interface.
- The **`R` channel** makes the dependency edges explicit and compiler-checked, so the boundary is real, not a convention people forget.

```ts
// The INTERFACE — small, stable, domain-named. This is what callers see.
class UserRepo extends Effect.Service<UserRepo>()("App/UserRepo", {
  effect: Effect.gen(function* () {
    const sql = yield* SqlClient        // ← all the complexity lives behind here
    return {
      findById: (id: UserId) => /* ...joins, mapping, caching... */,
      create: (input: NewUser) => /* ...validation, transaction... */
    }
  }),
  dependencies: [SqlClient.Default]
}) {}
```

**Design the interface deliberately; delegate the implementation.** You (or your reviewer) should own the shape of the service — its methods, their domain types, their error types. The body behind it is where you can let an AI or a teammate work more freely, *because the boundary is testable and type-checked*. This is the single highest-leverage habit in an Effect codebase.

❌ Don't expose a dozen loosely-related free functions that each take a `db` and a `logger` — that's a shallow module; the wiring leaks everywhere.
✅ Do collect related functionality behind one service interface and hide the dependencies inside its layer.

---

## The layer graph IS your application architecture

In most frameworks the dependency wiring is implicit (imports, globals, a DI container configured by strings). In Effect it is a **typed value**: the composition of `Layer`s. The shape of that graph *is* your architecture, and the compiler checks it.

```
                ┌─────────────┐
                │  AppConfig  │   (leaf: reads env)
                └──────┬──────┘
                       │ provide
                ┌──────▼──────┐
                │  SqlClient  │   (scoped: owns the pool)
                └──────┬──────┘
            ┌──────────┼──────────┐ provide
       ┌────▼────┐ ┌───▼────┐ ┌───▼─────┐
       │UserRepo │ │OrderRepo│ │AuditLog │
       └────┬────┘ └───┬────┘ └───┬─────┘
            └─────┬─────┘          │ provide
            ┌─────▼─────┐    ┌─────▼─────┐
            │UserService│    │ Reporting │
            └───────────┘    └───────────┘
```

Each node is a service; each edge is a `Layer.provide`. The whole graph collapses into one `MainLive` layer with `RIn = never`, provided once at the edge. Properties that fall out for free:

- **One source of truth for wiring.** Want to know what the app depends on? Read `MainLive`.
- **Memoization.** A layer referenced by many consumers is built **once** and shared (see [Context, Services & Layers](05-context-layers.md)). `AppConfig` and the connection pool are singletons by construction, not by discipline.
- **Swappability at any node.** Provide a different layer producing the same tag → the whole subtree above it runs against the substitute. This is your test seam, your dev-vs-prod seam, your in-memory-vs-postgres seam.

```ts
// app/Main.ts — the wiring lives in ONE place
const MainLive = Layer.mergeAll(
  UserService.Default,
  Reporting.Default
).pipe(
  Layer.provide(SqlClient.Default),     // shared by everything above
  Layer.provide(AppConfig.Default)
)
```

---

## Run at the edge, describe everywhere else

An Effect program is a *description*. The boundary between "description" and "the running world" should be **exactly one place per entry point**.

```ts
// app/main.ts — the ONE place we run
import { NodeRuntime } from "@effect/platform-node"

program.pipe(Effect.provide(MainLive), NodeRuntime.runMain)
```

- A server, CLI, or worker: one `runMain` (see [Platform](14-platform.md)).
- A long-lived host you don't control (a UI framework, a test harness, a Lambda): build a `ManagedRuntime` from `MainLive` once and run many effects against it (see [Creating & running](02-creating-running.md)).

❌ Don't call `Effect.runPromise`/`runSync` inside business logic, services, or loops. Nested runs discard the context, error channel, interruption, and tracing — you lose everything Effect gives you.
✅ Do thread effects all the way up and run once at the top. If the `R` channel won't collapse to `never`, that's the compiler telling you a dependency is unwired — fix the graph, don't cast.

---

## Errors are domain vocabulary (ubiquitous language)

The `E` channel is where Effect lets you encode the *domain's* failure modes as named, typed values. Treat error tags as part of your **ubiquitous language** — the shared glossary between you, your teammates, the AI, and the code. A well-named tagged error documents a real business outcome.

```ts
import { Data } from "effect"

class UserNotFound extends Data.TaggedError("UserNotFound")<{ id: UserId }> {}
class EmailAlreadyTaken extends Data.TaggedError("EmailAlreadyTaken")<{ email: string }> {}
class PaymentDeclined extends Data.TaggedError("PaymentDeclined")<{ code: string }> {}
```

Now a signature *reads like a spec*: `Effect<Receipt, PaymentDeclined | InsufficientFunds, PaymentGateway>` tells the reader exactly what can go wrong and what it needs. `catchTag("PaymentDeclined", ...)` handles one named case exhaustively. See [Error management](04-errors.md).

**The distinction that organizes your error handling:** typed `E` = expected outcomes your callers should reason about. *Defects* (`die`) = bugs and broken invariants that should crash loudly, not be modeled. Don't pollute the `E` channel with "this should never happen."

❌ Don't use `Error` with a string message for everything — `catch (e: unknown)` is back, and the type tells the reader nothing.
✅ Do name each recoverable failure as a `Data.TaggedError` in domain terms, and let unexpected failures be defects.

---

## How to lay out files

Effect's own repo convention (and the one that scales): **one module per file, co-locate the contract with its implementation and its errors.** A service file is a deep module — the file *is* the boundary.

```
src/
  domain/                 # ubiquitous language: types, schemas, errors — no I/O
    User.ts               #   UserId (branded), User (Schema.Class), NewUser
    errors.ts             #   UserNotFound, EmailAlreadyTaken, ...
  services/               # one deep module per file: tag + interface + Default layer
    SqlClient.ts
    UserRepo.ts           #   class UserRepo extends Effect.Service<…> { … }
    UserService.ts
    PaymentGateway.ts
  http/                   # the edge: adapt HTTP <-> domain (thin)
    api.ts                #   HttpApi definition (schema-first)
    handlers.ts           #   HttpApiBuilder groups — call services, no business logic
  Main.ts                 # MainLive: the layer graph, assembled once
  main.ts                 # runMain(program.pipe(Effect.provide(MainLive)))
```

Guidelines:

- **`domain/` has no dependencies on `services/`.** Pure types, `Schema`, branded ids, tagged errors. This is the vocabulary everything else speaks.
- **Each service file exports its tag-class and its `.Default` layer.** Co-locate `static Test`/`Live` variants if you hand-author layers. The file's public surface is the interface; everything else is private.
- **The edge is thin.** HTTP handlers, CLI commands, UI event handlers *translate* between the outside world and your services — decode input with `Schema`, call a service, encode the result. No domain logic lives at the edge.
- **`Main.ts` is the only file that knows the whole graph.** Keep the wiring out of leaf modules.

### Feature-oriented vs layer-oriented

For larger apps, group by **feature/bounded-context** first, then by role inside it:

```
src/
  users/    { domain.ts, UserRepo.ts, UserService.ts, http.ts }
  billing/  { domain.ts, PaymentGateway.ts, BillingService.ts, http.ts }
  shared/   { SqlClient.ts, AppConfig.ts, Telemetry.ts }
  Main.ts
```

A feature exposes a small set of services (its public interface) and a `FeatureLive` layer; `Main.ts` composes the features. This keeps each bounded context a deep module of its own.

---

## Keep Effect at the core; adapt at the boundaries

Your *domain and services* should be Effect all the way down — that's where typed errors, context, and interruption pay off. At the boundaries you meet the non-Effect world; wrap it explicitly:

| Boundary | Adapt with |
| --- | --- |
| A `Promise`-returning SDK | `Effect.tryPromise({ try, catch })` — name the failure |
| A callback / event emitter | `Effect.async` |
| Untrusted input (HTTP body, env, file) | `Schema.decodeUnknown*` → typed value or `ParseError` |
| Config / secrets | `Config` + `Redacted` (see [Schema & Config](11-schema.md)) |
| A UI framework (React/Solid) | a `ManagedRuntime`, or `@effect-atom` (see [effect-atom](18-effect-atom.md)) |
| Time / randomness | `Clock`, `Effect.sleep`, `Random` — never `Date.now`/`setTimeout`/`Math.random` directly (keeps code testable with `TestClock`) |

Wrapping at the edge means the *inside* stays pure and composable, and the messy parts are isolated to small, obvious adapters.

### Adopting Effect in an existing codebase

The boundary table above describes the steady state. Getting there from a non-Effect codebase is the same idea applied one module at a time — Effect is designed to be adopted inward-out, and a half-migrated codebase is a legitimate resting place, not a failure.

1. **Pick one leaf with real pain** — the module with retries, timeouts, flaky I/O, or tangled error handling. That's where Effect pays for itself immediately; a CRUD passthrough won't show you anything.
2. **Give it a service interface, not a rewrite.** Wrap the existing implementation with `Effect.tryPromise`/`Effect.async` behind a `Tag`, and name the failures as tagged errors. The old code keeps working; the new interface is what callers migrate to.
3. **Keep exactly one `runPromise` at each call site**, where the non-Effect caller invokes it. Build a single `ManagedRuntime` for the process and reuse it — never `Effect.runPromise` a fresh layer graph per call, or you rebuild (and re-acquire) your services every time. → [Creating & running](02-creating-running.md)
4. **Push the boundary outward.** When a caller of that service is itself converted, delete its `runPromise` and let it `yield*` instead. The runtime edge migrates up the call tree; the number of edges shrinks over time.
5. **Convert error handling before convenience code.** The payoff is concentrated in the `E` channel; a module converted without naming its failures gets you the ceremony and none of the benefit.

❌ Don't convert bottom-up module by module in dependency order — you'll build a large Effect surface nothing runs yet.
✅ Do convert along one vertical slice at a time (one request path, one job), so every step ships.

---

## Project setup

- **`strict: true` is mandatory.** Effect's inference leans on strict null checks and variance; without it `E`/`R` inference silently degenerates.
- **Target ES2022 or later** (Effect's own build does), so generators and class fields aren't downlevelled — `Effect.gen` runs on native generators.
- **`@effect/language-service`** — the editor plugin the Effect repo itself enables. It makes hovers print the three channels readably instead of expanded internals, and adds Effect-aware diagnostics and refactors. Add it under `compilerOptions.plugins` and point `namespaceImportPackages` at `effect` plus the `@effect/*` packages you use:

```jsonc
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2022",
    "plugins": [
      { "name": "@effect/language-service", "namespaceImportPackages": ["effect", "@effect/platform"] }
    ]
  }
}
```

- **`@effect/eslint-plugin`** adds Effect-specific lint rules on top; optional, useful on a team.
- One copy of `effect` in the tree. Two (via a mismatched peer dep) produce tag identities that don't match, and the symptom is a service that "won't provide" with an error naming the tag you *did* provide. → [Pitfalls](17-pitfalls.md)

---

## Testing falls out of the architecture

You don't design for testability separately — deep modules with layer boundaries *are* the testability. To test `UserService`, provide a fake `UserRepo` layer; the service is unchanged.

```ts
const UserRepoTest = Layer.succeed(UserRepo, UserRepo.make({
  findById: (id) => Effect.succeed(new User({ id, name: "Test" }))
}))

it.effect("greets the user", () =>
  Effect.gen(function* () {
    const msg = yield* UserService.greet(UserId("u1"))
    assert.strictEqual(msg, "Hello, Test!")
  }).pipe(Effect.provide(UserService.DefaultWithoutDependencies.pipe(Layer.provide(UserRepoTest)))))
```

(`.DefaultWithoutDependencies` because `UserService` declares `dependencies` — providing into plain `.Default` would keep the real repo. → [Context, Services & Layers](05-context-layers.md))

Time-dependent code (retries, timeouts, schedules) tests *instantly* with `TestClock` because you used `Effect.sleep`/`Schedule` instead of real timers. See [Testing](15-testing.md). **If a thing is hard to test, the boundary is in the wrong place** — that's design feedback, act on it.

---

## Habits that keep the codebase changeable

- **Invest in the design every day** (Kent Beck). Each change either improves the module boundaries or erodes them; there's no neutral. When a service interface starts sprouting unrelated methods, split it.
- **Name everything in the domain's language.** Services, methods, tagged errors, branded ids. The names are the interface; an AI reasons over your codebase far better when they're precise and consistent.
- **Prefer fewer, deeper services** over many shallow ones. A `Billing` service with a focused interface beats `chargeCard`, `refund`, `getInvoice`, `listInvoices` scattered as free functions sharing five dependencies.
- **Make the dependency explicit, then hide it.** If a function reaches for a global, give it a service. If a service's internals leak into callers, tighten the interface.
- **Let `R = never` be your "fully wired" check.** A green type at the entry point means every dependency is accounted for.
- **Keep comments scarce** (Effect's own rule): clear names and types over prose. Comment only genuinely non-obvious logic.

---

## See also

- [Mental model](01-mental-model.md) — the `A / E / R` channels these patterns rest on
- [Context, Services & Layers](05-context-layers.md) — the mechanics of services, layers, and the graph
- [Error management](04-errors.md) — typed errors as domain vocabulary
- [Resources & Scope](06-resources-scope.md) — scoped layers for app-lifetime resources
- [Platform](14-platform.md) — `runMain`, HTTP API, the application edge
- [Testing](15-testing.md) — swapping layers, `TestClock`
- [Pitfalls](17-pitfalls.md) — the anti-patterns that erode all of the above
