# Schema & Config — Effect v3

When you reach for this: validating unknown data at runtime, serializing/deserializing between wire and domain types, reading typed configuration from the environment, and generating JSON Schema / Arbitrary test data from a single source of truth.

> **v3 import**: Schema lives in the core `effect` package.
> ```ts
> import { Schema } from "effect"          // ✅ v3
> import { Schema } from "@effect/schema"  // ❌ old v2 package
> ```

---

## Contents

- [The `Schema<A, I, R>` Triple](#the-schemaa-i-r-triple)
- [Primitives](#primitives)
- [Structs](#structs)
- [Records](#records)
- [Arrays & Tuples](#arrays-tuples)
- [Union, Literal, Enums](#union-literal-enums)
- [NullOr / UndefinedOr / NullishOr](#nullor-undefinedor-nullishor)
- [Transformations](#transformations)
- [Filters & Refinements](#filters-refinements)
- [Branding](#branding)
- [Classes](#classes)
- [Decoding & Encoding](#decoding-encoding)
- [ParseResult & Error Formatting](#parseresult-error-formatting)
- [Annotations](#annotations)
- [JSON Schema](#json-schema)
- [Arbitrary (fast-check)](#arbitrary-fast-check)
- [Schema.equivalence](#schemaequivalence)
- [Schema.pretty](#schemapretty)
- [Config Module](#config-module)
- [ConfigProvider](#configprovider)
- [`Redacted` — Secrets](#redacted-secrets)
- [Common Recipes](#common-recipes)
- [See also](#see-also)


## The `Schema<A, I, R>` Triple

```ts
interface Schema<in out A, in out I = A, out R = never>
```

| Parameter | Meaning |
|-----------|---------|
| `A` | **Type** — the decoded / domain value |
| `I` | **Encoded** — the wire / serialized form |
| `R` | **Context** — Effect services required during parsing |

When `I = A` (default) the schema is an identity transform (no serialization gap). When `R = never` parsing is pure.

Extract static types:

```ts
import { Schema } from "effect"

const S = Schema.Struct({ id: Schema.Number, name: Schema.String })

type User     = typeof S.Type     // { readonly id: number; readonly name: string }
type Encoded  = typeof S.Encoded  // { readonly id: number; readonly name: string }
// Equivalently:
type User2    = Schema.Schema.Type<typeof S>
```

---

## Primitives

```ts
Schema.String       // string
Schema.Number       // number
Schema.Boolean      // boolean
Schema.BigIntFromSelf  // bigint (identity — already bigint)
Schema.BigInt       // bigint, encoded as string  (transform)
Schema.Date         // Date (identity)
Schema.DateFromSelf // Date (identity — alias)
Schema.DateFromString  // Date decoded from ISO string  (transform)
Schema.Null         // null
Schema.Undefined    // undefined
Schema.Void         // void
Schema.Never        // never
Schema.Unknown      // unknown
Schema.Any          // any
Schema.Object       // object
Schema.SymbolFromSelf  // symbol
```

---

## Structs

```ts
const User = Schema.Struct({
  id:   Schema.Number,
  name: Schema.String,
})
// Type:    { readonly id: number; readonly name: string }
// Encoded: { readonly id: number; readonly name: string }
```

### `optional` / `optionalWith`

```ts
const Config = Schema.Struct({
  // plain optional — type is `string | undefined`, encoded is `string | undefined`
  host: Schema.optional(Schema.String),

  // exact optional — no `undefined` in type, just absent
  port: Schema.optionalWith(Schema.Number, { exact: true }),

  // optional with default on decode
  retries: Schema.optionalWith(Schema.Number, { default: () => 3 }),

  // optional nullable — accepts null or absent on input
  region: Schema.optionalWith(Schema.String, { nullable: true }),

  // decode as Option<string>
  token: Schema.optionalWith(Schema.String, { as: "Option" }),
})
```

Defaults apply both during **decoding** and when using `.make()` on the struct.

### `partial` / `required`

```ts
const Partial = Schema.partial(User)   // all fields become optional + undefined
const Required = Schema.required(SomePartialSchema)
```

### `pick` / `omit`

```ts
const Minimal = User.pick("name")
const WithoutId = User.omit("id")
```

### `extend` (merge two structs)

```ts
const Extended = Schema.extend(User, Schema.Struct({ role: Schema.String }))
```

---

## Records

```ts
const StrMap = Schema.Record({ key: Schema.String, value: Schema.Number })
// Type: { readonly [x: string]: number }
```

---

## Arrays & Tuples

```ts
const Strings  = Schema.Array(Schema.String)         // readonly string[]
const NonEmpty = Schema.NonEmptyArray(Schema.String)  // [string, ...string[]]

// Tuple with optional element and rest
const T = Schema.Tuple(
  [Schema.String, Schema.optionalElement(Schema.Number)],
  Schema.Boolean   // rest element
)
```

---

## Union, Literal, Enums

```ts
// Union
const StringOrNum = Schema.Union(Schema.String, Schema.Number)

// Literal — single or multi-value
const Direction = Schema.Literal("north", "south", "east", "west")
// Type: "north" | "south" | "east" | "west"

// Enum
enum Color { Red = "red", Blue = "blue" }
const ColorSchema = Schema.Enums(Color)
// Type: Color.Red | Color.Blue
```

---

## NullOr / UndefinedOr / NullishOr

```ts
const MaybeString = Schema.NullOr(Schema.String)     // string | null
const OptString   = Schema.UndefinedOr(Schema.String) // string | undefined
const Nullish     = Schema.NullishOr(Schema.String)   // string | null | undefined
```

---

## Transformations

### `transform` (pure)

```ts
const NumberFromString = Schema.transform(
  Schema.String,      // From
  Schema.Number,      // To
  {
    strict: true,
    decode: (s) => Number(s),
    encode: (n) => String(n),
  }
)
// Schema<number, string>
```

### `transformOrFail` (effectful / fallible)

```ts
import { ParseResult, Schema } from "effect"

const StrictNumberFromString = Schema.transformOrFail(
  Schema.String,
  Schema.Number,
  {
    strict: true,
    decode: (s, _options, ast) => {
      const n = Number(s)
      return isNaN(n)
        ? ParseResult.fail(new ParseResult.Type(ast, s, "not a number"))
        : ParseResult.succeed(n)
    },
    encode: (n) => ParseResult.succeed(String(n)),
  }
)
```

### `compose` — chain two compatible schemas

```ts
const A = Schema.compose(Schema.String, Schema.NumberFromString)
// Schema<number, string>
```

---

## Filters & Refinements

`filter` adds a predicate constraint without changing the type:

```ts
const NonEmpty = Schema.String.pipe(
  Schema.filter((s) => s.length > 0, { message: () => "must not be empty" })
)

// Type-predicate form — narrows the type
type Even = number & { readonly _tag: "Even" }
const EvenNumber = Schema.Number.pipe(
  Schema.filter((n): n is Even => n % 2 === 0)
)
```

`filter` return types:
- `true` / `undefined` / `void` — pass
- `false` — fail with default message
- `string` — fail with that message
- `ParseResult.ParseIssue` — fail with custom issue
- `Option<ParseResult.ParseIssue>` — `None` = pass, `Some` = fail

Built-in filters (via `Schema.String.pipe(...)` etc.):

```ts
Schema.String.pipe(Schema.minLength(1))
Schema.String.pipe(Schema.maxLength(100))
Schema.String.pipe(Schema.pattern(/^[a-z]+$/))
Schema.String.pipe(Schema.email())
Schema.Number.pipe(Schema.int())
Schema.Number.pipe(Schema.between(0, 100))
Schema.Number.pipe(Schema.positive())
Schema.Number.pipe(Schema.nonNaN())
Schema.Array(Schema.String).pipe(Schema.minItems(1))
```

---

## Branding

```ts
import { Schema } from "effect"

const UserId = Schema.Number.pipe(Schema.brand("UserId"))
type UserId = typeof UserId.Type  // number & Brand<"UserId">

// .make() validates and brands
const id = UserId.make(42)

// fromBrand — bring existing Brand.Constructor into schema
import { Brand } from "effect"
type PositiveInt = number & Brand.Brand<"PositiveInt">
const PositiveInt = Brand.refined<PositiveInt>(
  (n) => Number.isInteger(n) && n > 0,
  (n) => Brand.error(`Expected positive integer, got ${n}`)
)
const PositiveIntSchema = Schema.Number.pipe(Schema.fromBrand(PositiveInt))
```

---

## Classes

Classes give you **opaque type + constructor + schema** in one declaration. They extend `Data.Class` so instances get structural equality for free.

### `Schema.Class`

```ts
class User extends Schema.Class<User>("User")({
  id:   Schema.Number,
  name: Schema.String,
}) {
  get display() {
    return `${this.name} (${this.id})`
  }
}

// Usage
const u = new User({ id: 1, name: "Alice" })
// u instanceof User === true
// Schema.decodeUnknownSync(User)({ id: 1, name: "Alice" }) returns User instance
```

### `Schema.TaggedClass`

```ts
class AdminUser extends Schema.TaggedClass<AdminUser>()("AdminUser", {
  id:   Schema.Number,
  name: Schema.String,
}) {}

// _tag is automatically set and excluded from the constructor
const a = new AdminUser({ id: 1, name: "Bob" })
a._tag // "AdminUser"
```

### `Schema.TaggedError`

```ts
class NotFoundError extends Schema.TaggedError<NotFoundError>()(
  "NotFoundError",
  { id: Schema.Number, resource: Schema.String }
) {
  get message() { return `${this.resource} ${this.id} not found` }
}

// Can be yielded in Effect.gen
const effect = Effect.gen(function*() {
  yield* new NotFoundError({ id: 1, resource: "User" })
})
```

### `Schema.TaggedRequest`

Used with `Effect.request` / `RequestResolver`. Encodes both request payload and its success/failure schemas.

```ts
class GetUser extends Schema.TaggedRequest<GetUser>()("GetUser", {
  payload: { id: Schema.Number },
  success: Schema.Struct({ name: Schema.String }),
  failure: Schema.String,
}) {}
```

**Why classes vs plain structs?**
- Branded opaque type — `instanceof` checks work
- Structural equality built in (from `Data.Class`)
- Class body allows custom methods
- Serializable protocol integration (TaggedRequest)

---

## Decoding & Encoding

All decoders follow the same signature pattern. **Prefer `decodeUnknown*` when input is truly unknown** (e.g., JSON.parse output). Use `decode*` when input is typed as `I`.

### Synchronous (throws `ParseError`)

```ts
import { Schema } from "effect"

const result = Schema.decodeUnknownSync(User)({ id: 1, name: "Alice" })
// throws on failure

Schema.encodeSync(User)(userInstance)
Schema.validateSync(User)(anyValue)  // only checks Type side
```

### Either (pure, no Effect)

```ts
const either = Schema.decodeUnknownEither(User)({ id: 1, name: "Alice" })
// Either<User, ParseError>

Schema.encodeUnknownEither(User)(userInstance)
```

### Promise

```ts
await Schema.decodeUnknownPromise(User)(json)
await Schema.encodePromise(User)(user)
```

### Effect (for schemas with `R != never`)

```ts
const effect = Schema.decodeUnknown(User)(json)
// Effect<User, ParseError, R>

Schema.encode(User)(user)    // Effect<I, ParseError, R>
```

### Guards & Asserts

```ts
const isUser = Schema.is(User)          // (u: unknown) => u is User
Schema.asserts(User)(unknownValue)      // asserts unknownValue is User (throws)
```

---

## ParseResult & Error Formatting

```ts
import { ParseResult, Schema } from "effect"

// TreeFormatter — human-readable string (default)
const str = ParseResult.TreeFormatter.formatErrorSync(parseError)

// ArrayFormatter — machine-readable flat array
const issues = ParseResult.ArrayFormatter.formatErrorSync(parseError)
// Array<{ _tag, path: PropertyKey[], message: string }>

// Async (for schemas with async message annotations)
const strAsync = await Effect.runPromise(
  ParseResult.TreeFormatter.formatError(parseError)
)
```

`ParseResult` exports these issue constructors for use in `transformOrFail`:
- `ParseResult.succeed(a)` — returns `Effect<A, never>`
- `ParseResult.fail(issue)` — returns `Effect<never, ParseIssue>`
- `ParseResult.mapError(effect, fn)` — maps `ParseIssue` to `ParseError`
- `new ParseResult.Type(ast, actual, message?)` — type mismatch issue
- `new ParseResult.Missing(ast)` — missing field
- `new ParseResult.Unexpected(actual, ast)` — unexpected key

---

## Annotations

Annotations enrich schemas with metadata for documentation, JSON Schema, arbitrary generation, and custom error messages.

```ts
const EmailString = Schema.String.pipe(
  Schema.filter((s) => s.includes("@")),
).annotations({
  identifier: "EmailString",
  title: "Email Address",
  description: "A valid email address",
  examples: ["user@example.com"],
  default: "user@example.com",
  message: () => "must be a valid email address",
  jsonSchema: { format: "email" },
})
```

Annotation keys (corresponding to AST annotation IDs):

| Key | Purpose |
|-----|---------|
| `identifier` | Unique name, used in error messages |
| `title` | Short label |
| `description` | Longer prose |
| `examples` | Array of valid values |
| `default` | Default value hint |
| `documentation` | Full docs string |
| `jsonSchema` | Raw JSON Schema overrides |
| `message` | Custom error message (string or `(issue) => string`) |
| `missingMessage` | Custom message for missing required field |
| `arbitrary` | Custom fast-check arbitrary |
| `pretty` | Custom pretty printer |
| `equivalence` | Custom equivalence |

---

## JSON Schema

```ts
import { JSONSchema, Schema } from "effect"

const jsonSchema = JSONSchema.make(User)
// { "$schema": "...", "type": "object", "properties": {...}, ... }
```

---

## Arbitrary (fast-check)

```ts
import { Arbitrary, FastCheck, Schema } from "effect"

const arb = Arbitrary.make(User)            // FastCheck.Arbitrary<User>
const lazyArb = Arbitrary.makeLazy(User)    // (fc) => FastCheck.Arbitrary<User>

// Generate samples
FastCheck.sample(arb, 5)
```

---

## Schema.equivalence

Derives structural equality from the schema:

```ts
import { Schema } from "effect"

const eq = Schema.equivalence(User)
// Equivalence<User>
eq(user1, user2)  // boolean
```

---

## Schema.pretty

Derives a human-readable string printer:

```ts
import { Pretty, Schema } from "effect"

const printer = Pretty.make(User)
printer(user)  // "{ id: 1, name: \"Alice\" }"
```

---

## Config Module

When you reach for this: reading typed, validated configuration from environment variables, config files, or other sources. `Config<A>` is also an `Effect<A, ConfigError>`.

### Primitives

```ts
import { Config, Effect } from "effect"

const host    = Config.string("HOST")
const port    = Config.integer("PORT")
const debug   = Config.boolean("DEBUG")
const retries = Config.number("MAX_RETRIES")
const secret  = Config.redacted("API_KEY")    // Redacted<string>
const timeout = Config.duration("TIMEOUT")    // Duration
const level   = Config.logLevel("LOG_LEVEL")  // LogLevel
const appUrl  = Config.url("APP_URL")         // URL
const listenPort = Config.port("LISTEN_PORT") // number (validated 1-65535)
```

### Defaults

```ts
const port = Config.withDefault(Config.integer("PORT"), 3000)
// or
const port = Config.integer("PORT").pipe(Config.withDefault(3000))
```

### Optional

```ts
const maybeRegion = Config.option(Config.string("AWS_REGION"))
// Config<Option<string>>
```

### Arrays

```ts
const tags = Config.array(Config.string(), "TAGS")
// Reads "TAGS" as comma-separated list by default
```

### Nesting

```ts
const dbConfig = Config.all({
  host: Config.string("HOST"),
  port: Config.integer("PORT"),
}).pipe(Config.nested("DB"))
// Reads DB_HOST and DB_PORT
```

### `Config.all` — combining configs

```ts
const AppConfig = Config.all({
  host:  Config.string("HOST"),
  port:  Config.integer("PORT"),
  debug: Config.withDefault(Config.boolean("DEBUG"), false),
})
// Config<{ host: string; port: number; debug: boolean }>
```

### `Config.map` / `Config.mapAttempt`

```ts
const upperHost = Config.string("HOST").pipe(
  Config.map((s) => s.toUpperCase())
)

// mapAttempt — catches thrown exceptions, turns them into config errors
const parsed = Config.string("MY_JSON").pipe(
  Config.mapAttempt((s) => JSON.parse(s))
)
```

### `Config.mapOrFail`

```ts
import { Either, ConfigError, Config } from "effect"

const validated = Config.string("ENV").pipe(
  Config.mapOrFail((s) =>
    s === "production" || s === "development"
      ? Either.right(s as "production" | "development")
      : Either.left(ConfigError.InvalidData(["ENV"], `unknown env: ${s}`))
  )
)
```

### Validating in a branded way

```ts
import { Brand, Config } from "effect"

type Port = number & Brand.Brand<"Port">
const Port = Brand.refined<Port>(
  (n) => Number.isInteger(n) && n > 0 && n < 65536,
  (n) => Brand.error(`${n} is not a valid port`)
)

const portConfig = Config.integer("PORT").pipe(
  Config.branded(Port)
)
```

### Reading config in an Effect

```ts
const program = Effect.gen(function*() {
  const cfg = yield* AppConfig
  // cfg.host, cfg.port, cfg.debug are all typed
})
```

### Failing fast at startup

Make config a **leaf layer** every other layer depends on. Because layers are built before the program runs, a missing or malformed variable aborts startup rather than surfacing on the first request that happens to need it.

```ts
import { Config, Effect, Layer } from "effect"

class AppConfig extends Effect.Service<AppConfig>()("App/Config", {
  effect: Config.all({
    host: Config.string("HOST"),
    port: Config.port("PORT"),                    // validated 1–65535
    apiKey: Config.redacted("API_KEY")
  })
}) {}
// `Config<A>` IS an `Effect<A, ConfigError>`, so it can be the service body directly.

const MainLive = ServerLive.pipe(Layer.provide(AppConfig.Default))

// A ConfigError here fails the LAYER BUILD — the server never starts listening.
Layer.launch(MainLive).pipe(NodeRuntime.runMain)
```

The error is a `ConfigError`, carrying the path it was looking for — a missing variable renders as `(Missing data at PORT: "Expected PORT to exist in the process context")`, and `runMain` logs it and exits non-zero. Two ways to make that message better:

- **Group related config under a name** with `Config.nested("DATABASE")(…)`, so the path in the error says which subsystem is misconfigured.
- **Validate values, don't just read them** — `Config.mapOrFail` lets you fail with your own message (see above), which beats a downstream `NaN` or a connection refused ten seconds later.

❌ Don't read config lazily inside a request handler — a typo in an env var then becomes a runtime 500 instead of a failed boot.
✅ Do put every `Config` read in a layer that the entrypoint provides.

---

## ConfigProvider

`ConfigProvider` is the service that backs `Config` loading. The default uses environment variables. You can override it for tests or custom sources.

### Built-in providers

```ts
import { ConfigProvider } from "effect"

// From env (default — uppercase keys, _ as path delimiter, , as seq delimiter)
const envProvider = ConfigProvider.fromEnv()

// From a Map (great for tests)
const mapProvider = ConfigProvider.fromMap(
  new Map([
    ["HOST", "localhost"],
    ["PORT", "5432"],
    ["DB_HOST", "db.internal"],
  ])
)

// From JSON object
const jsonProvider = ConfigProvider.fromJson({
  host: "localhost",
  port: 5432,
})
```

### Providing a custom ConfigProvider in tests

```ts
import { ConfigProvider, Effect, Layer } from "effect"

const TestConfig = Layer.setConfigProvider(
  ConfigProvider.fromMap(new Map([["PORT", "9000"]]))
)

const test = program.pipe(Effect.provide(TestConfig))
```

### Combinators

```ts
// Fallback chain
const provider = ConfigProvider.orElse(primary, () => fallback)

// Normalize key casing
const snakeCase = ConfigProvider.snakeCase(ConfigProvider.fromEnv())
const upperCase = ConfigProvider.upperCase(ConfigProvider.fromEnv())

// Nest all keys under a prefix
const nested = ConfigProvider.nested(ConfigProvider.fromEnv(), "APP")
// now CONFIG reads APP_CONFIG, etc.
```

---

## `Redacted` — Secrets

`Redacted<A>` wraps a value so it prints as `<redacted>` in logs and `toString()`. The actual value is accessible only via `Redacted.value()`.

```ts
import { Config, Redacted, Effect } from "effect"

const program = Effect.gen(function*() {
  const apiKey = yield* Config.redacted("API_KEY")
  // apiKey is Redacted<string>

  console.log(apiKey)           // "<redacted>"
  const raw = Redacted.value(apiKey)  // "actual-secret-value"

  // Pass raw string to HTTP client, etc.
})
```

```ts
// Create manually
const secret = Redacted.make("hunter2")

// Compare without exposing
Redacted.isRedacted(secret) // true
```

❌ Don't extract `Redacted.value()` at the top of your program and store it in a plain variable — the whole point is to keep it wrapped until the last moment.

✅ Pass the `Redacted<string>` through your layers; only extract in the single place that makes the HTTP call or DB connection.

---

## Common Recipes

### JSON round-trip

```ts
const encode = Schema.encodeUnknownSync(User)
const decode = Schema.decodeUnknownSync(User)

const json = JSON.stringify(encode(user))
const back = decode(JSON.parse(json))
```

### Validate a webhook body

```ts
app.post("/webhook", async (req, res) => {
  const result = Schema.decodeUnknownEither(WebhookPayload)(req.body)
  if (Either.isLeft(result)) {
    res.status(400).json({ error: ParseResult.TreeFormatter.formatErrorSync(result.left) })
    return
  }
  await processWebhook(result.right)
})
```

### Optional field with a computed default

```ts
const Config = Schema.Struct({
  timeout: Schema.optionalWith(Schema.Number, {
    default: () => 30_000,
    exact: true,
  }),
})
// timeout is required in the Type, optional in Encoded
```

---

## See also

- `ParseResult` source: `/packages/effect/src/ParseResult.ts`
- `JSONSchema` source: `/packages/effect/src/JSONSchema.ts`
- `Arbitrary` source: `/packages/effect/src/Arbitrary.ts`
- `ConfigProvider` source: `/packages/effect/src/ConfigProvider.ts`
- Effect docs: https://effect.website/docs/schema/introduction
- Effect docs: https://effect.website/docs/configuration
