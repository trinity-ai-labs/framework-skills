<!-- verified: effect@9.9.9 -->
# Good chapter

Use `Effect.gen` and `Effect.succeed`, plus `Effect.void` (a reserved word export).
Nested access `Effect.Service.Default` checks only `Effect.Service`.
Ordinary dotted text is ignored: `console.log`, `process.env`, `foo.bar`, `Unknown.thing`.
JS globals that share a module name stay valid: `Array.from`.
A `Router.onlyInRpc` symbol exists in one of two Router modules.
A path such as `effect/Effect.ts` or `Effect.d.ts` is not a symbol.
Prose outside code, like Effect.notReal, is not checked.

```ts
import * as Effect from "effect/Effect"
const program = Effect.gen(function* () {
  console.log(process.env.HOME)
  return yield* Effect.succeed(1)
})
```
