<!-- verified: effect@4.0.0 -->
# Stability: depending on what may break

> **When you reach for this:** you are about to use an export from a module you do not know, you are choosing how to declare `effect` in `package.json`, or an upgrade to a newer 4.x is on the table. This chapter is the depth behind step 3 of the router (`../SKILL.md`): what each tier lets a release break, how to read an export's tier, and how to keep a breaking minor release confined to a few files.

In the v4 pre-releases an unstable module announced itself with an `unstable` segment in its import path. In 4.0.0 it does not: unstable code is imported from ordinary paths, the same `effect/<group>/<Module>` shape as stable code, and a release can change it without a major version. The discipline below replaces the signal the path used to give.

---

## The tiers, and what each lets a release break

The policy is upstream's, in `MIGRATION.md` of `Effect-TS/effect` ("Unstable Module System"); the package does not state it. It reads:

> `@stability unstable` means an API may receive breaking changes in minor releases. `@stability experimental` means it may receive breaking changes across patch versions. APIs without a stability tag follow strict semver.

| Tier | Marked in the type definitions | A release may break it in |
| --- | --- | --- |
| stable | no `@stability` tag | a major release only (strict semver) |
| `unstable` | `@stability unstable` | a minor release |
| `experimental` | `@stability experimental` | a patch release |

Upstream adds one rule that is easy to miss: **an export that exposes a third-party dependency is tagged `unstable` regardless of its module**, because that dependency's own releases can change it. Upstream gives accessors to underlying clients, options typed as the dependency's options, and re-exports of the dependency, and says the generated provider schemas in the `@effect/ai-*` packages and the `@effect/opentelemetry` integration are covered.

**What 4.0.0 actually contains.** Of the two weaker tiers, only `unstable` occurs. No export recorded for `effect@4.0.0` is tagged `experimental`, so that tier is policy with no instance yet; do not write code that assumes one exists, and do not read its absence as a promise about later releases. Treat any `experimental` you meet in a newer version as the weakest guarantee there is.

---

## The tier is per export, so look it up

Moving the unstable modules to ordinary paths did not stabilize them, and it removed the one cheap signal. Three things follow, all true of 4.0.0:

- **A stable module can hold unstable exports.** The root `Schema` module is stable, but 120 of its 686 recorded exports are tagged `unstable` (the network-address schemas such as `IpAddress` among them). `String` from the same module is stable.
- **A module group can mix.** `effect/encoding` holds `Base64` and `Hex`, which are stable, beside `Sse` and `Ndjson`, which are not. `effect/testing` has the stable `TestClock` and the unstable `TestSchema`.
- **A single module can mix.** In `effect/http-api/HttpApiClient`, two type members are stable and the rest of the module is not.
- **Upstream's own list of unstable modules is not complete or current.** `MIGRATION.md` lists a `jsonschema` group; in 4.0.0 `effect/JsonSchema` is a root module with no unstable export. It leaves out a group the package tags wholesale (`effect/net`). The router's list is a version-stamped hint for the same reason.

So the tier is never inferred from a path, a module name or a list. Ask the installed package, with the router's script:

```sh
node <skill-dir>/scripts/stability.mjs effect/Schema IpAddress --from <package directory>
# unstable
node <skill-dir>/scripts/stability.mjs effect/Schema String --from <package directory>
# stable
```

`<skill-dir>` is the directory the skill's `SKILL.md` is in, and `--from` is the package whose `effect` you are resolving (in a monorepo, the one you are editing). The script reads the export's own `@stability` tag from the installed type definitions. It exits non-zero for an export that does not exist, which makes it a check that you have the name right as well as a tier lookup.

Things worth knowing when you run it:

- **Look up every export you have not already looked up**, and especially anything outside the core root modules (`effect/http`, `effect/sql`, `effect/rpc`, `effect/cli`, `effect/ai` and the like) and anything that hands you a third-party client or takes its options.
- **A tier answers for one version.** Do not carry it over to another install: an unstable export can be promoted, changed, or removed, and the next section is about noticing.
- **Your own code is not the only consumer.** Companion packages such as `@effect/platform-node` import unstable `effect` modules internally (for example `effect/socket/Socket`, `effect/http/Headers`), so a project that touches no unstable export of its own still runs on them. That bears on pinning, below.

When you rely on an unstable or experimental export, say so to the person you are working for. The next section is what makes that cost bounded, and it is a decision they should know they are carrying.

---

## Pin `effect` exactly, and keep the companions on the same version

A caret range on `effect` means "any 4.x", which permits exactly the minor release that can break an unstable export. So:

- **If you use an unstable or experimental export, pin `effect` to an exact version**, with no `^` or `~`, and upgrade it deliberately.
- **Pin every companion package to the same exact version.** Everything that remains separate (`@effect/platform-node`, `@effect/platform-bun`, `@effect/vitest`, `@effect/opentelemetry`, `@effect/sql-*`, `@effect/ai-*`, `@effect/atom-*`) shares `effect`'s version number: with `effect@4.0.0` the matching driver is `@effect/sql-pg@4.0.0`. Checked with `npm view <package>@4.0.0 peerDependencies` for `@effect/platform-node`, `@effect/platform-bun`, `@effect/vitest`, `@effect/opentelemetry`, `@effect/sql-pg`, `@effect/ai-openai` and `@effect/atom-react`: each declares `effect: ^4.0.0`, which any 4.x satisfies. **The package manager will not stop you installing `effect@4.1.0` beside a companion at `4.0.0`.** Keeping them in step is your job, not the resolver's.
- **Bump them as one change.** Moving only `effect` leaves a companion compiled against the old unstable surface it imports.
- **A lockfile is not a pin.** `npm update`, a dependency bot or a fresh install with a changed range moves it. The exact version in `package.json` is what survives.

```json
{
  "dependencies": {
    "effect": "4.0.0",
    "@effect/platform-node": "4.0.0"
  }
}
```

If you use only stable exports and no companion, a caret is within the policy. Most real applications have at least a platform package, so pin by default and relax only when you have checked.

When you do bump: read `reference/changes/<version>.md` for the new release (see the last section), re-run the stability script for every unstable export you rely on, and typecheck before anything else.

---

## Wrap unstable modules behind a thin local module

Pinning stops a surprise; it does not make the eventual upgrade cheap. The second half of the discipline is to import each unstable group from **one place in your code**, so a breaking minor release is a change to that place and not to every file that touches HTTP.

```ts
// file: src/infra/Fetcher.ts. The only file in the reference app that imports effect/http.
import { Context, Data, Effect, Layer } from "effect"
import * as HttpClient from "effect/http/HttpClient"

export class FetchError extends Data.TaggedError("FetchError")<{
  readonly url: string
  readonly cause: unknown
}> {}

// What the rest of the app sees: a small contract in the app's own terms.
export class Fetcher extends Context.Service<Fetcher, {
  readonly text: (url: string) => Effect.Effect<string, FetchError>
}>()("app/infra/Fetcher") {
  // The unstable dependency appears only in this layer's requirement,
  // which is satisfied at the edge where the program is wired.
  static readonly layer: Layer.Layer<Fetcher, never, HttpClient.HttpClient> = Layer.effect(
    Fetcher,
    Effect.gen(function*() {
      const client = yield* HttpClient.HttpClient
      return Fetcher.of({
        text: (url) =>
          client.get(url).pipe(
            Effect.flatMap((response) => response.text),
            Effect.mapError((cause) => new FetchError({ url, cause }))
          )
      })
    })
  )
}
```

What makes this work, and what makes it fail:

- **The local module owns the import and exposes your own types and errors.** `FetchError` and the `text` signature are yours. The unstable `HttpClient` types never appear in a function signature the rest of the app calls. If they do, the unstable surface has leaked and the wrapper has bought nothing.
- **Keep it thin.** One function or one small service per thing the app actually does. A wrapper that re-exports the whole group, or recreates its API one-for-one, moves every breaking change into your code unchanged and adds a file to maintain.
- **Wrap by group, not by project.** Each unstable group you use (`http`, `sql`, `rpc`, ...) gets its own boundary. Where those boundaries sit in the layout, and how the layers they expose are assembled, is [Architecture](03-architecture.md)'s subject.
- **Do not wrap stable exports.** The wrapper's cost is justified only by what the policy lets a minor release break. A stable `Effect.map` behind your own module is noise.
- **Enforce the boundary cheaply.** A search that lists the files importing a group should list one. Run it for each group you depend on, from the project root:

```sh
grep -rln 'from "effect/http' src
# src/infra/Fetcher.ts
```

A pre-existing codebase with unstable imports scattered through it is the usual starting point. Move them behind the wrapper one group at a time, starting with the group whose companion packages you already pin.

The same applies to a single unstable export in an otherwise stable module: re-export it from your local module (`export { IpAddress } from ...`) so that the day it changes there is one import to fix.

---

## When the installed version is newer than anything recorded

Each chapter's first line is `<!-- verified: effect@<version> -->`, the release it was checked against. This chapter's judgments (the tiers, the policy, the shape of the discipline) outlast a release; the specific facts it cites (which export is unstable, what a module contains) are stamped to the version in that line and can be out of date against a newer install.

1. Run `node <skill-dir>/scripts/version.mjs <directory of the file you are editing>`. Compare it with the stamp.
2. If the installed version is newer, open `reference/changes/<version>.md` for each release after the stamp, up to and including the installed one. These are generated from a diff of the published packages, grouped by stability tier, so the unstable and experimental changes are the ones to read first.
3. **If a release has no file there, say so**, and do not guess what changed. The installed package is the source of truth: read its `AGENTS.md`, its `ai-docs/` and the type definitions, and run the stability script for what you rely on. A chapter's statement about an export that your install contradicts is the chapter's error.
4. Upstream's own record is `MIGRATION.md` and `migration/` at the release tag in `Effect-TS/effect`, and its `packages/tools/api-diff` is the tool that produces an API diff between two versions.
5. After the bump, re-run the stability script for each unstable export you depend on. A tier can move in either direction, and an export you wrapped may have become stable (the wrapper can go) or been removed.

---

## See also

- [Coming from v3](01-coming-from-v3.md): the shifts, including why the path no longer shows stability.
- [Architecture](03-architecture.md): where the local boundary around an unstable group sits, and how the layers it exposes are assembled.
- [Pitfalls](04-pitfalls.md): the mistakes that recur around dependencies, including ones that look like stability problems.
- The router, `../SKILL.md`: step 3 (the lookup) and step 5 (version drift), of which this chapter is the depth.
- Upstream: `MIGRATION.md` ("Unstable Module System") for the policy.
