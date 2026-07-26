# Effect Platform: HTTP API, HTTP Client, Platform Services, and Runtimes

When you reach for this: you need to build or consume HTTP APIs, access the filesystem, run subprocesses, or wire up a Node/Bun entrypoint.

Most platform APIs are in `@effect/platform` (runtime-agnostic) with concrete implementations in `@effect/platform-node` and `@effect/platform-bun`. Two adjacent first-party packages ship separately on npm rather than living inside `@effect/platform`, but round out the same "build a real backend" story: `@effect/sql` (typed database access, with per-dialect packages like `@effect/sql-pg`) and `@effect/rpc` (typed client/server contracts) — both build on `@effect/platform` services (e.g. `FileSystem`/`CommandExecutor` for migrations) rather than being part of it.

---

## Contents

- [The HTTP API (declarative, schema-first)](#the-http-api-declarative-schema-first)
- [HTTP Client (low-level)](#http-client-low-level)
- [Lower-level `HttpServer` / `HttpRouter`](#lower-level-httpserver-httprouter)
- [Platform Services](#platform-services)
- [`@effect/sql` — typed database access](#effectsql-typed-database-access)
- [`@effect/rpc` — typed client/server contracts](#effectrpc-typed-clientserver-contracts)
- [Workers — real off-main-thread parallelism](#workers-real-off-main-thread-parallelism)
- [Entrypoints: `runMain`](#entrypoints-runmain)
- [`@effect/cli`](#effectcli)
- [See also](#see-also)


## The HTTP API (declarative, schema-first)

The `HttpApi*` modules let you define an API once and reuse it for the server implementation, the client, and auto-generated Swagger docs.

```
HttpApi
├── HttpApiGroup
│   ├── HttpApiEndpoint
│   └── HttpApiEndpoint
└── HttpApiGroup
    └── HttpApiEndpoint
```

### 1. Define the API

```ts
import {
  HttpApi,
  HttpApiEndpoint,
  HttpApiGroup,
  HttpApiSchema
} from "@effect/platform"
import { Schema } from "effect"

// Domain schema
const User = Schema.Struct({
  id: Schema.Number,
  name: Schema.String
})

// Path param helper
const userIdParam = HttpApiSchema.param("id", Schema.NumberFromString)

// Define endpoints
const UsersGroup = HttpApiGroup.make("users")
  .add(
    HttpApiEndpoint.get("listUsers", "/users")
      .addSuccess(Schema.Array(User))
  )
  .add(
    HttpApiEndpoint.get("getUser")`/users/${userIdParam}`
      .addSuccess(User)
      .addError(Schema.String, { status: 404 })
  )
  .add(
    HttpApiEndpoint.post("createUser", "/users")
      .setPayload(Schema.Struct({ name: Schema.String }))
      .addSuccess(User, { status: 201 })
  )
  .add(
    HttpApiEndpoint.patch("updateUser")`/users/${userIdParam}`
      .setPayload(Schema.Struct({ name: Schema.String }))
      .addSuccess(User)
  )
  .add(
    HttpApiEndpoint.del("deleteUser")`/users/${userIdParam}`
    // no .addSuccess → defaults to 204 No Content
  )

// Assemble the full API
const MyApi = HttpApi.make("MyApi").add(UsersGroup)
```

Key `HttpApiEndpoint` methods:

| Method | Purpose |
|---|---|
| `.addSuccess(Schema, { status? })` | Success response schema (default 200) |
| `.addError(Schema, { status })` | Error response (adds to union) |
| `.setPayload(Schema)` | Request body (POST/PUT/PATCH) |
| `.setPath(Schema)` | Path parameter schema |
| `.setUrlParams(Schema)` | Query-string parameters |
| `.setHeaders(Schema)` | Request header schema (lowercase keys) |

For multipart file upload:

```ts
import { HttpApiSchema, Multipart } from "@effect/platform"
import { Schema } from "effect"

HttpApiEndpoint.post("upload", "/upload").setPayload(
  HttpApiSchema.Multipart(Schema.Struct({ files: Multipart.FilesSchema }))
).addSuccess(Schema.String)
```

### 2. Implement the handlers

```ts
import { HttpApiBuilder } from "@effect/platform"
import { Effect, Layer } from "effect"

const UsersGroupLive = HttpApiBuilder.group(MyApi, "users", (handlers) =>
  handlers
    .handle("listUsers", () =>
      Effect.succeed([{ id: 1, name: "Alice" }])
    )
    .handle("getUser", ({ path }) =>
      Effect.succeed({ id: path.id, name: "Bob" })
    )
    .handle("createUser", ({ payload }) =>
      Effect.succeed({ id: 99, name: payload.name })
    )
    .handle("updateUser", ({ path, payload }) =>
      Effect.succeed({ id: path.id, name: payload.name })
    )
    .handle("deleteUser", () => Effect.void)
)

// Combine into a single API layer
const MyApiLive = HttpApiBuilder.api(MyApi).pipe(
  Layer.provide(UsersGroupLive)
)
```

### 3. Serve it

```ts
import { HttpApiBuilder, HttpApiSwagger } from "@effect/platform"
import { NodeHttpServer, NodeRuntime } from "@effect/platform-node"
import { Layer } from "effect"
import { createServer } from "node:http"

const ServerLive = HttpApiBuilder.serve().pipe(
  Layer.provide(HttpApiSwagger.layer()),   // optional: /docs
  Layer.provide(MyApiLive),
  Layer.provide(NodeHttpServer.layer(createServer, { port: 3000 }))
)

Layer.launch(ServerLive).pipe(NodeRuntime.runMain)
```

For Bun, swap `NodeHttpServer` for `BunHttpServer` and `NodeRuntime.runMain` for `BunRuntime.runMain` (see Entrypoints below).

### 4. Derive a type-safe client

```ts
import { HttpApiClient, FetchHttpClient } from "@effect/platform"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const client = yield* HttpApiClient.make(MyApi, {
    baseUrl: "http://localhost:3000"
  })

  const users = yield* client.users.listUsers()
  const user  = yield* client.users.getUser({ path: { id: 1 } })
  const created = yield* client.users.createUser({ payload: { name: "Carol" } })
  console.log(users, user, created)
}).pipe(Effect.provide(FetchHttpClient.layer))
```

The client mirrors the API structure: `client.<groupName>.<endpointName>(request)`.

---

## HTTP Client (low-level)

Use `HttpClient` when you don't own the server's API definition.

```ts
import { FetchHttpClient, HttpClient, HttpClientRequest, HttpClientResponse } from "@effect/platform"
import { Effect, Schema } from "effect"

const ResponseSchema = Schema.Struct({ id: Schema.Number, name: Schema.String })

const program = Effect.gen(function* () {
  const client = yield* HttpClient.HttpClient

  // Simple GET
  const resp = yield* client.get("https://api.example.com/users/1")
  const user = yield* HttpClientResponse.schemaJson(ResponseSchema)(resp)

  // POST with JSON body
  const postResp = yield* client.post("https://api.example.com/users").pipe(
    // set body via request transformation
    Effect.flatMap((res) => HttpClientResponse.schemaJson(ResponseSchema)(res))
  )

  return user
}).pipe(Effect.provide(FetchHttpClient.layer))
```

Building requests:

```ts
import { HttpClientRequest } from "@effect/platform"
import { Schema } from "effect"

// Construct
const req = HttpClientRequest.post("https://api.example.com/users")

// Set JSON body (validated by Schema)
const withBody = yield* HttpClientRequest.schemaBodyJson(
  Schema.Struct({ name: Schema.String })
)(req, { name: "Alice" })

// Headers, auth
const withAuth = req.pipe(
  HttpClientRequest.bearerToken("mytoken"),
  HttpClientRequest.setHeader("X-Custom", "value")
)
```

Executing:

```ts
const client = yield* HttpClient.HttpClient

// Execute a pre-built request
const resp = yield* HttpClient.execute(client, req)

// Convenience methods
const getResp  = yield* client.get("https://...")
const postResp = yield* client.post("https://...")

// Parse body
const data = yield* HttpClientResponse.schemaJson(MySchema)(resp)
```

Retries and mapping:

```ts
import { HttpClient } from "@effect/platform"
import { Schedule } from "effect"

// Retry transient errors with a schedule
const resilient = client.pipe(
  HttpClient.retryTransient({ times: 3, schedule: Schedule.exponential("100 millis") })
)

// Map all requests (e.g. prepend a base URL)
const baseClient = client.pipe(
  HttpClient.mapRequest(HttpClientRequest.prependUrl("https://api.example.com"))
)

// Filter — fail if status is not 2xx
const strictClient = client.pipe(HttpClient.filterStatusOk)
```

HTTP client layers:

| Package | Layer |
|---|---|
| `@effect/platform` | `FetchHttpClient.layer` — Fetch API (browser / Bun / Deno) |
| `@effect/platform-node` | `NodeHttpClient.layer` — Node.js `http`/`https` |
| `@effect/platform-node` | `NodeHttpClient.layerUndici` — Undici (faster HTTP/1.1) |

---

## Lower-level `HttpServer` / `HttpRouter`

For cases where the declarative API is too heavy, build a router directly:

```ts
import { HttpRouter, HttpServerResponse, HttpServer } from "@effect/platform"
import { NodeHttpServer, NodeRuntime } from "@effect/platform-node"
import { Effect, Layer } from "effect"
import { createServer } from "node:http"

const router = HttpRouter.empty.pipe(
  HttpRouter.get("/health", HttpServerResponse.json({ ok: true })),
  HttpRouter.post("/echo", Effect.gen(function* () {
    const req = yield* HttpRouter.RouteContext
    const body = yield* req.request.json
    return yield* HttpServerResponse.json(body)
  }))
)

const ServerLive = HttpServer.serve(router).pipe(
  Layer.provide(NodeHttpServer.layer(createServer, { port: 3000 }))
)

Layer.launch(ServerLive).pipe(NodeRuntime.runMain)
```

`HttpServerResponse` constructors: `json`, `text`, `html`, `stream`, `file`, `empty`, `redirect`, `schemaJson`.

---

## Platform Services

### FileSystem

```ts
import { FileSystem } from "@effect/platform"
import { NodeFileSystem } from "@effect/platform-node"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const fs = yield* FileSystem.FileSystem

  const text = yield* fs.readFileString("data.json", "utf8")
  const obj  = JSON.parse(text)

  yield* fs.writeFileString("output.json", JSON.stringify(obj, null, 2))

  const stat = yield* fs.stat("data.json")
  console.log(stat.size)

  // Streaming
  const stream = fs.stream("large.bin")
}).pipe(Effect.provide(NodeFileSystem.layer))
```

Key methods: `readFile`, `readFileString`, `writeFile`, `writeFileString`, `remove`, `rename`, `copy`, `mkdir`, `readDirectory`, `stat`, `stream`, `sink`, `open` (for `File` handle with `read`/`write`/`seek`).

### Path

```ts
import { Path } from "@effect/platform"
import { NodePath } from "@effect/platform-node"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const path = yield* Path.Path
  const full = path.join(__dirname, "assets", "logo.png")
  const ext  = path.extname(full)
  const dir  = path.dirname(full)
  return { full, ext, dir }
}).pipe(Effect.provide(NodePath.layer))
```

### KeyValueStore

Simple string key → string value persistence:

```ts
import { KeyValueStore } from "@effect/platform"
import { NodeKeyValueStore } from "@effect/platform-node"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const store = yield* KeyValueStore.KeyValueStore
  yield* store.set("token", "abc")
  const val = yield* store.get("token")  // Option<string>
  yield* store.remove("token")
}).pipe(Effect.provide(NodeKeyValueStore.layerFileSystem("./data/kv")))
```

Layers: `KeyValueStore.layerMemory`, `NodeKeyValueStore.layerFileSystem(dir)`.

For typed values use `KeyValueStore.layerSchema(Schema, underlying)`.

### Command / CommandExecutor (subprocesses)

```ts
import { Command } from "@effect/platform"
import { NodeCommandExecutor } from "@effect/platform-node"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  // Capture stdout as string
  const out = yield* Command.make("git", "log", "--oneline", "-5").pipe(
    Command.string
  )

  // Stream stdout lines
  const lines = yield* Command.make("cat", "/etc/hosts").pipe(
    Command.lines
  )

  // Exit code only
  const code = yield* Command.make("npm", "test").pipe(
    Command.exitCode
  )

  // Pipe commands
  const piped = yield* Command.make("ls", "-la").pipe(
    Command.pipeTo(Command.make("grep", ".ts")),
    Command.string
  )

  return { out, lines, code }
}).pipe(Effect.provide(NodeCommandExecutor.layer))
```

Key functions: `Command.make`, `Command.string`, `Command.lines`, `Command.stream`, `Command.streamLines`, `Command.exitCode`, `Command.pipeTo`, `Command.feed`, `Command.env`, `Command.workingDirectory`.

### Terminal

```ts
import { Terminal } from "@effect/platform"
import { NodeTerminal } from "@effect/platform-node"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const terminal = yield* Terminal.Terminal
  yield* terminal.display("Enter your name: ")
  const input = yield* terminal.readLine
  yield* terminal.display(`Hello, ${input}!\n`)
}).pipe(Effect.provide(NodeTerminal.layer))
```

---

## `@effect/sql` — typed database access

A separate package (not `@effect/platform`). `@effect/sql` is dialect-agnostic (`SqlClient`, `SqlSchema`, `Model`, `Migrator`); dialect packages like `@effect/sql-pg` and `@effect/sql-sqlite-node` provide the `SqlClient` implementation and connection layer.

### The `SqlClient` tag

Every query runs through the `SqlClient` service — it's also a tagged-template function:

```ts
import { SqlClient } from "@effect/sql"
import { Effect } from "effect"

const program = Effect.gen(function* () {
  const sql = yield* SqlClient.SqlClient
  const people = yield* sql<{ id: number; name: string }>`SELECT id, name FROM people`
})
```

### Constructing a client layer

```ts
import { PgClient } from "@effect/sql-pg"
import { Config } from "effect"

// Static config
const PgLive = PgClient.layer({ database: "my_app" })

// From Config (env vars, secrets, ...)
const PgLiveConfig = PgClient.layerConfig({ database: Config.string("DATABASE") })
```

```ts
import { SqliteClient } from "@effect/sql-sqlite-node"

const SqliteLive = SqliteClient.layer({ filename: "db.sqlite" })
```

Both layers provide the dialect-agnostic `SqlClient` tag *and* the dialect-specific one (`PgClient`/`SqliteClient`) for dialect-only features (e.g. Postgres `.listen`/`.notify`).

### Tagged-template queries: parameterized by construction

Every value interpolated into a `` sql`...` `` template becomes a bound parameter — never string-concatenated into the SQL text. That's what makes injection structurally impossible, as long as you don't drop to `sql.unsafe`:

```ts
const statement = sql`SELECT * FROM people LIMIT ${limit}`
// compiles to: SELECT * FROM people LIMIT $1  (bound parameter, not inlined)
```

❌ Don't build queries with string interpolation:

```ts
sql.unsafe(`SELECT * FROM people WHERE name = '${name}'`) // injectable
```

✅ Do interpolate values straight into the template — the compiler binds them:

```ts
sql`SELECT * FROM people WHERE name = ${name}`
```

Helpers for the parts of a query that aren't plain values:

| Helper | Purpose |
|---|---|
| `sql(identifier)` | Quotes a table/column name, e.g. `` sql`SELECT * FROM ${sql(table)}` `` |
| `sql.in(column, values)` / `sql.in(values)` | `IN (...)` clause |
| `sql.insert(record \| records)` | INSERT value list |
| `sql.update(record, omit?)` | UPDATE `SET` list |
| `sql.and([...])` / `sql.or([...])` | Combine fragments |
| `sql.unsafe(sqlString, params?)` | Escape hatch — bypasses interpolation binding; only use with static SQL |

A tagged-template call returns a `Statement<A>`, which is itself `Effect<ReadonlyArray<A>, SqlError>` — `yield*` it directly, or use `.stream`, `.values`, `.compile()`.

### `SqlSchema` — decode rows into a `Schema`

```ts
import { SqlSchema, SqlClient } from "@effect/sql"
import { Schema, Effect } from "effect"

const Person = Schema.Struct({ id: Schema.Number, name: Schema.String })

const getById = Effect.gen(function* () {
  const sql = yield* SqlClient.SqlClient
  const findById = SqlSchema.findOne({
    Request: Schema.Number,
    Result: Person,
    execute: (id) => sql`SELECT * FROM people WHERE id = ${id}`
  })
  return yield* findById(1) // Effect<Option<Person>, ParseError | SqlError>
})
```

`SqlSchema.findAll` decodes every row (`ReadonlyArray<A>`); `SqlSchema.findOne` decodes zero-or-one (`Option<A>`); `SqlSchema.single` decodes exactly one row (fails with `NoSuchElementException` on zero rows).

### `Model` — one field definition, every variant

`Model.Class` generates `select`/`insert`/`update`/`json`/`jsonCreate`/`jsonUpdate` schema variants from a single field definition, so one model backs your DB rows, insert payloads, and JSON API shapes instead of four hand-written schemas.

### `Migrator` — forward-only, TypeScript migrations

Migrations are plain Effects, one per file, loaded and run in numeric order:

```ts
import { PgMigrator } from "@effect/sql-pg"
import { Layer } from "effect"
import { fileURLToPath } from "node:url"

const MigratorLive = PgMigrator.layer({
  loader: PgMigrator.fromFileSystem(fileURLToPath(new URL("migrations", import.meta.url))),
  schemaDirectory: "src/migrations" // where to write the `_schema.sql` dump
}).pipe(Layer.provide(PgLive))
```

`@effect/sql-sqlite-node` exposes the identical shape via `SqliteMigrator.layer` / `SqliteMigrator.fromFileSystem`.

---

## `@effect/rpc` — typed client/server contracts

Another separate package. `@effect/rpc` gives you an end-to-end typed contract between a TypeScript client and server — request/response (and streaming) shapes defined once, shared by both sides.

Choose `@effect/rpc` over `HttpApi` (above) when **both ends are TypeScript** and you want wire format, serialization, and streaming handled for you. Choose `HttpApi` when you're publishing a documented REST-ish API for external or non-TS consumers — it gets you Swagger/OpenAPI docs for free; `@effect/rpc` does not.

### Define requests, group them

```ts
import { Rpc, RpcGroup } from "@effect/rpc"
import { Schema } from "effect"

class User extends Schema.Class<User>("User")({
  id: Schema.String,
  name: Schema.String
}) {}

class UserRpcs extends RpcGroup.make(
  Rpc.make("UserList", { success: User, stream: true }),
  Rpc.make("UserById", {
    success: User,
    error: Schema.String,
    payload: { id: Schema.String }
  }),
  Rpc.make("UserCreate", { success: User, payload: { name: Schema.String } })
) {}
```

### Implement the handlers

```ts
import { Effect, Stream } from "effect"

const UsersLive = UserRpcs.toLayer(
  Effect.gen(function* () {
    // ... yield* a repository service, etc.
    return {
      UserList: () => Stream.fromIterable(users),
      UserById: ({ id }) => findUser(id),   // Effect<User, string>
      UserCreate: ({ name }) => createUser(name)
    }
  })
)
```

### Serve it

```ts
import { HttpRouter } from "@effect/platform"
import { NodeHttpServer, NodeRuntime } from "@effect/platform-node"
import { RpcSerialization, RpcServer } from "@effect/rpc"
import { Layer } from "effect"
import { createServer } from "node:http"

const RpcLayer = RpcServer.layer(UserRpcs).pipe(Layer.provide(UsersLive))

const HttpProtocol = RpcServer.layerProtocolHttp({ path: "/rpc" }).pipe(
  Layer.provide(RpcSerialization.layerNdjson)
)

const Main = HttpRouter.Default.serve().pipe(
  Layer.provide(RpcLayer),
  Layer.provide(HttpProtocol),
  Layer.provide(NodeHttpServer.layer(createServer, { port: 3000 }))
)

NodeRuntime.runMain(Layer.launch(Main))
```

### Consume it

```ts
import { FetchHttpClient } from "@effect/platform"
import { RpcClient, RpcSerialization } from "@effect/rpc"
import { Effect, Layer, Stream } from "effect"

const ProtocolLive = RpcClient.layerProtocolHttp({
  url: "http://localhost:3000/rpc"
}).pipe(Layer.provide([FetchHttpClient.layer, RpcSerialization.layerNdjson]))

const program = Effect.gen(function* () {
  const client = yield* RpcClient.make(UserRpcs)
  const users = yield* Stream.runCollect(client.UserList({}))
  const created = yield* client.UserCreate({ name: "Carol" })
}).pipe(Effect.scoped, Effect.provide(ProtocolLive))
```

`client.<rpcName>(payload)` returns a `Stream` for RPCs declared `stream: true`, otherwise an `Effect`.

### Serialization

`RpcSerialization` picks the wire format the client and server must agree on: `layerJson`, `layerNdjson` (newline-delimited, needed for streaming responses over plain HTTP), or `layerMsgPack`.

---

## Workers — real off-main-thread parallelism

Fibers are **cooperative**: they multiplex onto the single JS thread and yield only at effect boundaries. A synchronous, CPU-bound computation (image processing, parsing a huge payload, crypto) blocks *every other fiber* until it returns — `Effect.fork`/`Effect.all` don't give you a second CPU, they only interleave I/O-bound work on one. For real parallelism you need an actual OS thread. `@effect/platform`'s `Worker`/`WorkerRunner`, backed by `@effect/platform-node`'s `worker_threads` bindings, are the escape hatch.

### The worker side (runs inside the spawned thread)

```ts
// worker/range.ts
import { WorkerRunner } from "@effect/platform"
import { NodeRuntime, NodeWorkerRunner } from "@effect/platform-node"
import { Effect, Layer, Stream } from "effect"

const WorkerLive = Effect.gen(function* () {
  yield* WorkerRunner.make((n: number) => Stream.range(0, n))
  yield* Effect.addFinalizer(() => Effect.log("worker closed"))
}).pipe(Layer.scopedDiscard, Layer.provide(NodeWorkerRunner.layer))

NodeRuntime.runMain(NodeWorkerRunner.launch(WorkerLive))
```

`WorkerRunner.make(handler)` registers the function that answers every message from the main thread; returning a `Stream` lets one request push back multiple results.

### The main-thread side: a worker pool

```ts
import { Worker } from "@effect/platform"
import { NodeWorker, NodeRuntime } from "@effect/platform-node"
import { Context, Effect, Layer, Stream } from "effect"
import * as WT from "node:worker_threads"

interface RangePool { readonly _: unique symbol }
const RangePool = Context.GenericTag<RangePool, Worker.WorkerPool<number, never, number>>("RangePool")

const PoolLive = Worker.makePoolLayer(RangePool, { size: 3 }).pipe(
  Layer.provide(NodeWorker.layer(() => new WT.Worker("./worker/range.js")))
)

Effect.gen(function* () {
  const pool = yield* RangePool
  yield* pool.execute(1000).pipe(Stream.runForEach((n) => Effect.log(n)))
}).pipe(Effect.provide(PoolLive), NodeRuntime.runMain)
```

`WorkerPool` gives you `execute` (a `Stream` of results), `executeEffect` (a single result), and `broadcast` (fire to every worker). Fixed-size pools take `{ size }`; elastic pools take `{ minSize, maxSize, timeToLive }`.

For request/response messages typed with `Schema` instead of raw values, reach for `Worker.makeSerialized` / `makePoolSerialized` with `Schema.TaggedRequest` messages — same shape, decoded/encoded automatically.

---

## Entrypoints: `runMain`

### Node.js

```ts
import { NodeRuntime } from "@effect/platform-node"
import { Layer } from "effect"

const MainLive = ServerLive.pipe(
  Layer.provide(DatabaseLive),
  Layer.provide(ConfigLive)
)

// Runs the layer, handles SIGINT/SIGTERM for graceful shutdown
Layer.launch(MainLive).pipe(NodeRuntime.runMain)
```

### Bun

```ts
import { BunRuntime } from "@effect/platform-bun"
import { Layer } from "effect"

Layer.launch(MainLive).pipe(BunRuntime.runMain)
```

Both `NodeRuntime.runMain` and `BunRuntime.runMain` are the same signature (`RunMain`). They:
- Run the effect to completion
- Handle `SIGINT` / `SIGTERM` → interrupt the fiber for graceful shutdown
- Log unhandled defects to stderr
- Exit with code 0 on success, 1 on failure

**Node vs Bun differences to be aware of:**

| Concern | Node (`@effect/platform-node`) | Bun (`@effect/platform-bun`) |
|---|---|---|
| HTTP server | `NodeHttpServer.layer(createServer, { port })` | `BunHttpServer.layer({ port })` |
| HTTP client | `NodeHttpClient.layer` | `FetchHttpClient.layer` (Bun's fetch is native) |
| File system | `NodeFileSystem.layer` | `BunFileSystem.layer` |
| Context (for CLI) | `NodeContext.layer` | `BunContext.layer` |

### Graceful shutdown: what tears down, and in what order

On `SIGINT`/`SIGTERM`, `runMain` removes its own signal listeners and calls `fiber.unsafeInterruptAsFork(fiber.id())` on the main fiber — the same interruption machinery used everywhere else in Effect, not a special-cased shutdown path. Because listeners are removed on the *first* signal, **a second `SIGINT`/`SIGTERM` is not intercepted** — it falls through to Node's default (immediate kill), which is your escape hatch if shutdown hangs.

Interrupting the main fiber unwinds every `Scope` the running layer opened, running finalizers in **reverse order of acquisition** (see Finalizer ordering in `06-resources-scope.md`) — services started last shut down first.

**In-flight HTTP requests:** `NodeHttpServer`'s layer finalizer calls Node's `server.close()`, which itself stops accepting new connections and waits for existing ones to finish before its callback fires — so in-flight requests do get a chance to complete before the server's scope closes. There is, however, no Effect-level "drain with a grace period" API — if a client keeps a connection open, that finalizer waits indefinitely. Don't reach for an imaginary `HttpServer.drain`/`gracePeriod` option; if you need a hard cap, race your own release step against a timeout:

```ts
import { Effect, Duration } from "effect"

const releaseWithGracePeriod = <A, E, R>(
  release: Effect.Effect<A, E, R>,
  grace: Duration.DurationInput
) => release.pipe(Effect.race(Effect.sleep(grace)))
```

Apply this to resources you control directly (a job queue drain, an in-flight-request counter) when the platform's default unbounded wait isn't acceptable.

---

## `@effect/cli`

For CLI tools built on Effect:

```ts
import { Args, Command, Options } from "@effect/cli"
import { NodeContext, NodeRuntime } from "@effect/platform-node"
import { Console, Effect, Layer } from "effect"

// Define args and options
const fileArg  = Args.file({ exists: "yes" }).pipe(Args.withDescription("Input file"))
const verboseOpt = Options.boolean("verbose").pipe(Options.withAlias("v"))

// Define the command
const main = Command.make("mytool", { file: fileArg, verbose: verboseOpt }, ({ file, verbose }) =>
  Effect.gen(function* () {
    if (verbose) yield* Console.log(`Processing: ${file}`)
    // ... do work
  })
)

// Run
main.pipe(
  Command.withDescription("My CLI tool"),
  Command.run({ name: "mytool", version: "1.0.0" })
).pipe(
  Effect.provide(NodeContext.layer),
  NodeRuntime.runMain
)
```

Built-in flags provided automatically: `--help`, `--version`, `--completions`, `--log-level`, `--wizard`.

---

## See also

- `packages/platform/src/HttpApi.ts`, `HttpApiGroup.ts`, `HttpApiEndpoint.ts`
- `packages/platform/src/HttpApiBuilder.ts` — `serve`, `group`, `api`
- `packages/platform/src/HttpApiClient.ts` — `make`
- `packages/platform/src/HttpClient.ts` — `retryTransient`, `filterStatusOk`, `mapRequest`
- `packages/platform/src/HttpClientRequest.ts` — `schemaBodyJson`, `bearerToken`
- `packages/platform/src/HttpClientResponse.ts` — `schemaJson`
- `packages/platform-node/src/NodeRuntime.ts`, `packages/platform-bun/src/BunRuntime.ts`
- `packages/platform/src/Runtime.ts` — `makeRunMain`, `defaultTeardown`; `packages/platform-node-shared/src/internal/runtime.ts` — the actual SIGINT/SIGTERM handling
- `packages/platform/README.md` — full walkthrough with examples
- `packages/sql/src/SqlClient.ts`, `SqlSchema.ts`, `Model.ts`, `Migrator.ts` — `packages/sql/README.md` for more query-building examples
- `packages/sql-pg/src/PgClient.ts`, `PgMigrator.ts`; `packages/sql-sqlite-node/src/SqliteClient.ts`, `SqliteMigrator.ts`
- `packages/rpc/src/Rpc.ts`, `RpcGroup.ts`, `RpcServer.ts`, `RpcClient.ts`, `RpcSerialization.ts` — `packages/rpc/README.md` for the full quickstart (incl. middleware)
- `packages/platform/src/Worker.ts`, `WorkerRunner.ts`; `packages/platform-node/src/NodeWorker.ts`, `NodeWorkerRunner.ts`; `packages/platform-node/examples/worker.ts` for a runnable pool example
