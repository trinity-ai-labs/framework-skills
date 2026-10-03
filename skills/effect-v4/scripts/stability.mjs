#!/usr/bin/env node
// Print the stability tier of one export of the installed `effect` package.
//
//   node stability.mjs <module> <export> [--from <dir>]
//
//   <module>  an import specifier: effect, effect/Effect, effect/http/HttpRouter
//             (a bare path such as http/HttpRouter is read as effect/http/HttpRouter)
//   <export>  the exported name: Effect.map's module is effect/Effect and its export is map
//   --from    directory to resolve `effect` from (default: the current directory)
//
// Prints `stable`, `unstable` or `experimental` and exits 0. Exits 1 when the module
// or the export does not exist or the install is not Effect 4.x, 2 on bad usage.
//
// The tier is the export's own `@stability` tag in the installed type definitions;
// an export with no tag is stable. Nothing is inherited from a module header, because
// the compiler drops header comments from some definition files. Node built-ins only.

import fs from "node:fs"
import path from "node:path"

const TIERS = ["stable", "unstable", "experimental"] // least to most volatile (experimental may break in a patch); the most volatile wins a tie

const fail = (message, code = 1) => {
  console.error(`stability: ${message}`)
  process.exit(code)
}

const args = process.argv.slice(2)
let from = process.cwd()
const positional = []
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--from") {
    if (i + 1 >= args.length) fail("--from needs a directory", 2)
    from = path.resolve(args[++i])
  } else positional.push(args[i])
}
if (positional.length !== 2) {
  fail("usage: node stability.mjs <module> <export> [--from <dir>]   e.g. effect/http/HttpRouter make", 2)
}
let [moduleSpec, exportName] = positional
if (moduleSpec !== "effect" && !moduleSpec.startsWith("effect/")) moduleSpec = `effect/${moduleSpec}`

// --- find the installed package, the way Node resolution walks up ---------------------
let pkgDir = null
for (let dir = from; ; dir = path.dirname(dir)) {
  const candidate = path.join(dir, "node_modules", "effect")
  if (fs.existsSync(path.join(candidate, "package.json"))) {
    pkgDir = candidate
    break
  }
  if (path.dirname(dir) === dir) break
}
if (!pkgDir) fail(`no installed \`effect\` package found from ${from} (looked in every node_modules above it)`)
const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, "package.json"), "utf8"))
const major = parseInt(String(pkg.version).split(".")[0], 10)
if (!(major >= 4)) {
  fail(
    `found effect@${pkg.version} at ${pkgDir}. The @stability lookup reads Effect 4.x type definitions; ` +
      `a ${major}.x install does not use this convention. Use the effect-v3 skill for this project.`
  )
}

// --- resolve the module specifier through package.json "exports" ----------------------
const subpath = moduleSpec === "effect" ? "." : `./${moduleSpec.slice("effect/".length)}`
const target = (value) => {
  if (typeof value === "string") return value
  if (value && typeof value === "object") {
    for (const key of ["types", "import", "default"]) if (key in value) return target(value[key])
  }
  return null
}
const exportsMap = pkg.exports && typeof pkg.exports === "object" ? pkg.exports : {}
let resolved
if (subpath in exportsMap) {
  resolved = target(exportsMap[subpath])
} else {
  let best = null
  for (const key of Object.keys(exportsMap)) {
    const star = key.indexOf("*")
    if (star < 0) continue
    const prefix = key.slice(0, star)
    const suffix = key.slice(star + 1)
    if (!subpath.startsWith(prefix) || !subpath.endsWith(suffix) || subpath.length < key.length - 1) continue
    if (!best || prefix.length > best.prefix.length || (prefix.length === best.prefix.length && key.length > best.key.length)) {
      best = { key, prefix, suffix }
    }
  }
  if (best) {
    const matched = subpath.slice(best.prefix.length, subpath.length - best.suffix.length)
    const t = target(exportsMap[best.key])
    resolved = t === null ? null : t.replace(/\*/g, matched)
  }
}
const toDts = (file) => file.replace(/\.js$/, ".d.ts").replace(/\.mjs$/, ".d.mts").replace(/\.cjs$/, ".d.cts")
const moduleFile = resolved ? path.join(pkgDir, toDts(resolved)) : null
if (!moduleFile || !fs.existsSync(moduleFile)) {
  fail(
    `module \`${moduleSpec}\` does not exist in effect@${pkg.version}` +
      (resolved === null ? " (it is not exported by package.json)" : "")
  )
}

// --- read the declarations of one .d.ts -----------------------------------------------
const tagOf = (doc) => {
  if (!doc) return "stable"
  const m = /^\s*(?:\/\*\*\s*|\*\s*)@stability\s+(\w+)/m.exec(doc)
  return m ? m[1].toLowerCase() : "stable"
}

// Returns { named: Map<name, tier[]>, stars: string[] } for the top-level exports of a file.
const parseFile = (file) => {
  const lines = fs.readFileSync(file, "utf8").split("\n")
  const named = new Map()
  const stars = []
  const add = (name, tier) => {
    if (!named.has(name)) named.set(name, [])
    named.get(name).push(tier)
  }
  let pending = null // the JSDoc block directly before the next statement
  const declRe =
    /^export\s+(?:declare\s+)?(?:abstract\s+)?(?:const\s+enum|const|let|var|function\*?|class|namespace|module|enum|interface|type)\s+([A-Za-z_$][\w$]*)/
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (line.startsWith("/**")) {
      const start = i
      while (i + 1 < lines.length && !lines[i].includes("*/")) i++
      pending = lines.slice(start, i + 1).join("\n")
      continue
    }
    if (line.trim() === "" || line.startsWith("//")) continue
    if (!/^[A-Za-z]/.test(line)) continue // a continuation of a statement, never a start

    let m
    if (/^export\s*\{/.test(line)) {
      // export { /** doc */ a as b, c } [from "..."], possibly across several lines.
      // Scan character by character so a `}` or `,` inside a doc comment is not mistaken for syntax.
      let text = line
      const closes = (t) => {
        for (let p = 0; p < t.length; ) {
          if (t.startsWith("/*", p)) {
            const end = t.indexOf("*/", p + 2)
            if (end < 0) return false
            p = end + 2
          } else if (t[p] === "}") return true
          else p++
        }
        return false
      }
      while (!closes(text)) {
        if (i + 1 >= lines.length) break
        text += "\n" + lines[++i]
      }
      const items = []
      let doc = null
      let buf = ""
      const flush = () => {
        const spec = buf.replace(/^\s*type\s+/, "").trim()
        if (spec) items.push({ name: spec.split(/\s+as\s+/).pop().trim(), doc })
        buf = ""
        doc = null
      }
      for (let p = text.indexOf("{") + 1; p < text.length; ) {
        if (text.startsWith("/*", p)) {
          const end = text.indexOf("*/", p + 2) + 2
          doc = text.slice(p, end)
          p = end
        } else if (text[p] === "}") break
        else if (text[p] === ",") {
          flush()
          p++
        } else buf += text[p++]
      }
      flush()
      for (const item of items) add(item.name, tagOf(item.doc ?? pending))
    } else if ((m = /^export\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from/.exec(line))) {
      add(m[1], tagOf(pending))
    } else if ((m = /^export\s+\*\s+from\s+["']([^"']+)["']/.exec(line))) {
      stars.push(m[1])
    } else if ((m = declRe.exec(line))) {
      add(m[1], tagOf(pending))
    }
    pending = null
  }
  return { named, stars }
}

const lookup = (file, seen = new Set()) => {
  if (seen.has(file)) return null
  seen.add(file)
  const { named, stars } = parseFile(file)
  if (named.has(exportName)) return named.get(exportName)
  for (const star of stars) {
    const next = path.resolve(path.dirname(file), star.replace(/\.(m|c)?[jt]s$/, ".d.ts"))
    if (fs.existsSync(next)) {
      const hit = lookup(next, seen)
      if (hit) return hit
    }
  }
  return null
}

const tiers = lookup(moduleFile)
if (!tiers) fail(`\`${exportName}\` is not exported by \`${moduleSpec}\` in effect@${pkg.version}`)
const distinct = [...new Set(tiers)]
const tier = distinct.sort((a, b) => TIERS.indexOf(b) - TIERS.indexOf(a))[0]
if (distinct.length > 1) {
  console.error(`stability: ${moduleSpec} ${exportName} has declarations of different tiers (${distinct.join(", ")}); reporting the most volatile`)
}
console.log(tier)
