#!/usr/bin/env node
// Print the `effect` version a directory resolves to.
//
//   node version.mjs [dir]        dir defaults to the current directory
//
// Stdout is the bare version (for example 4.0.0) and nothing else; where it came from goes
// to stderr. Resolution walks up from `dir` through every node_modules, as Node does, so in
// a monorepo each package resolves its own copy. When nothing is installed it falls back to
// a lockfile: package-lock.json / npm-shrinkwrap.json, pnpm-lock.yaml, yarn.lock (v1 and
// Berry) and the text bun.lock. A binary bun.lockb cannot be read here and is reported.
// Exits 1 when no version can be resolved. Node built-ins only.

import fs from "node:fs"
import path from "node:path"

const start = path.resolve(process.argv[2] ?? process.cwd())
if (process.argv.length > 3 || start.startsWith("-")) {
  console.error("usage: node version.mjs [dir]")
  process.exit(2)
}
if (!fs.existsSync(start)) {
  console.error(`version: ${start} does not exist`)
  process.exit(1)
}

const read = (file) => {
  try {
    return fs.readFileSync(file, "utf8")
  } catch {
    return null
  }
}
const ancestors = (dir) => {
  const out = []
  for (let d = dir; ; d = path.dirname(d)) {
    out.push(d)
    if (path.dirname(d) === d) return out
  }
}
const done = (version, source) => {
  console.error(`version: ${source}`)
  console.log(version)
  process.exit(0)
}

// 1. Installed: the nearest node_modules/effect above `start`.
for (const dir of ancestors(start)) {
  const text = read(path.join(dir, "node_modules", "effect", "package.json"))
  if (!text) continue
  try {
    const v = JSON.parse(text).version
    if (v) done(v, `installed in ${path.join(dir, "node_modules", "effect")}`)
  } catch {
    // a package.json that does not parse is not an install; keep looking
  }
}

// 2. Not installed: what the lockfile pins. Which spec the nearest package.json asks for
// disambiguates a lockfile holding several versions.
let wanted = null
let packageRoot = start
for (const dir of ancestors(start)) {
  const text = read(path.join(dir, "package.json"))
  if (!text) continue
  try {
    const j = JSON.parse(text)
    const spec = j.dependencies?.effect ?? j.devDependencies?.effect ?? j.peerDependencies?.effect ?? j.optionalDependencies?.effect
    if (spec) {
      wanted = spec
      packageRoot = dir
      break
    }
  } catch {
    // ignore
  }
}

const unreadable = []
const notes = []
const rel = (root) => path.relative(root, start).split(path.sep).filter(Boolean)

const fromPackageLock = (text, root) => {
  const lock = JSON.parse(text)
  const pkgs = lock.packages
  if (pkgs) {
    // npm's resolution: <dir>/node_modules/effect, then each parent's, then the root's.
    const parts = rel(root)
    for (let n = parts.length; n >= 0; n--) {
      const key = [...parts.slice(0, n), "node_modules", "effect"].join("/")
      if (pkgs[key]?.version) return pkgs[key].version
    }
    return null
  }
  return lock.dependencies?.effect?.version ?? null // lockfileVersion 1
}

const fromPnpmLock = (text, root) => {
  const lines = text.split("\n")
  const indent = (l) => l.length - l.trimStart().length
  const clean = (v) => v.trim().replace(/^['"]|['"]$/g, "").replace(/\(.*$/, "").replace(/^link:.*/, "")
  // Direct dependency of one importer block (or of the top level in older lockfiles).
  const directIn = (from, to, base) => {
    for (let i = from; i < to; i++) {
      if (lines[i].trim() !== "effect:" && !/^\s+effect:\s*\S/.test(lines[i])) continue
      if (indent(lines[i]) !== base) continue
      const inline = /^\s+effect:\s*(\S.*)$/.exec(lines[i])
      if (inline) return clean(inline[1])
      for (let j = i + 1; j < to && indent(lines[j]) > indent(lines[i]); j++) {
        const m = /^\s+version:\s*(.+)$/.exec(lines[j])
        if (m) return clean(m[1])
      }
    }
    return null
  }
  const impAt = lines.findIndex((l) => l === "importers:")
  if (impAt >= 0) {
    let end = lines.length
    for (let i = impAt + 1; i < lines.length; i++) if (lines[i] && indent(lines[i]) === 0) { end = i; break }
    const blocks = []
    for (let i = impAt + 1; i < end; i++) {
      const m = /^ {2}(\S.*):\s*$/.exec(lines[i])
      if (m) blocks.push({ name: m[1].replace(/^['"]|['"]$/g, ""), at: i })
    }
    const parts = rel(root)
    let best = null
    for (const b of blocks) {
      const bp = b.name === "." ? [] : b.name.split("/")
      if (bp.length <= parts.length && bp.every((p, k) => p === parts[k]) && (!best || bp.length > best.len)) {
        best = { ...b, len: bp.length }
      }
    }
    if (best) {
      const next = blocks.find((b) => b.at > best.at)
      const v = directIn(best.at + 1, next ? next.at : end, 6)
      if (v) return v
    }
  } else {
    const v = directIn(0, lines.length, 4)
    if (v) return v
  }
  // Not a direct dependency of this importer: look at the resolved packages.
  const versions = new Set()
  for (const l of lines) {
    const m = /^\s+['"]?(?:\/)?effect[@/](\d[^'"():\s]*)['"]?(?:\(.*\))?:\s*$/.exec(l)
    if (m) versions.add(m[1])
  }
  if (versions.size === 1) {
    notes.push("pnpm-lock.yaml lists effect only as a transitive dependency")
    return [...versions][0]
  }
  if (versions.size > 1) notes.push(`pnpm-lock.yaml holds several effect versions (${[...versions].join(", ")}) and none is a direct dependency here`)
  return null
}

const fromYarnLock = (text) => {
  const found = [] // { descriptors, version }
  let current = null
  for (const line of text.split("\n")) {
    if (line && !/^\s/.test(line) && line.endsWith(":") && !line.startsWith("#")) {
      const descriptors = line.slice(0, -1).split(",").map((d) => d.trim().replace(/^['"]|['"]$/g, ""))
      current = descriptors.some((d) => d.startsWith("effect@")) ? { descriptors, version: null } : null
      if (current) found.push(current)
    } else if (current) {
      const m = /^\s+version:?\s+["']?([^"'\s]+)["']?\s*$/.exec(line)
      if (m) current.version = m[1]
    }
  }
  const entries = found.filter((e) => e.version)
  if (entries.length === 0) return null
  if (wanted) {
    const hit = entries.find((e) => e.descriptors.some((d) => d === `effect@${wanted}` || d === `effect@npm:${wanted}`))
    if (hit) return hit.version
  }
  const versions = [...new Set(entries.map((e) => e.version))]
  if (versions.length === 1) return versions[0]
  notes.push(`yarn.lock holds several effect versions (${versions.join(", ")}) and none matches ${wanted ? `the declared range ${wanted}` : "a declared range"}`)
  return null
}

const fromBunLock = (text) => {
  // bun.lock is JSONC: strip comments (outside strings) and trailing commas, then parse.
  let out = ""
  for (let i = 0, inStr = false; i < text.length; i++) {
    const c = text[i]
    if (inStr) {
      out += c
      if (c === "\\") out += text[++i]
      else if (c === '"') inStr = false
    } else if (c === '"') {
      inStr = true
      out += c
    } else if (c === "/" && text[i + 1] === "/") {
      while (i < text.length && text[i] !== "\n") i++
      out += "\n"
    } else if (c === "/" && text[i + 1] === "*") {
      i = text.indexOf("*/", i + 2) + 1
    } else out += c
  }
  const lock = JSON.parse(out.replace(/,(\s*[}\]])/g, "$1"))
  const pkgs = lock.packages ?? {}
  const idOf = (key) => {
    const id = pkgs[key]?.[0]
    const m = typeof id === "string" ? /^effect@(.+)$/.exec(id) : null
    return m ? m[1] : null
  }
  const direct = idOf("effect")
  if (direct) return direct
  const nested = Object.keys(pkgs).filter((k) => k.endsWith("/effect") && idOf(k)).map(idOf)
  const versions = [...new Set(nested)]
  if (versions.length === 1) return versions[0]
  if (versions.length > 1) notes.push(`bun.lock holds several effect versions (${versions.join(", ")})`)
  return null
}

const readers = [
  ["package-lock.json", fromPackageLock],
  ["npm-shrinkwrap.json", fromPackageLock],
  ["pnpm-lock.yaml", fromPnpmLock],
  ["yarn.lock", fromYarnLock],
  ["bun.lock", fromBunLock]
]

for (const dir of ancestors(start)) {
  for (const [name, reader] of readers) {
    const file = path.join(dir, name)
    const text = read(file)
    if (text === null) continue
    let version = null
    try {
      version = reader(text, dir)
    } catch (e) {
      notes.push(`${file} could not be parsed (${e.message})`)
    }
    if (version) {
      done(version, `effect is not installed here; ${version} is the version ${file} pins. Install dependencies to confirm what actually resolves.`)
    }
  }
  if (fs.existsSync(path.join(dir, "bun.lockb"))) unreadable.push(path.join(dir, "bun.lockb"))
}

console.error(`version: could not resolve an effect version from ${start}`)
console.error("  - no node_modules/effect in this directory or any parent")
for (const f of unreadable) {
  console.error(`  - ${f} is a binary lockfile this script cannot read; run \`bun install --save-text-lockfile\` or install dependencies, then run this again`)
}
for (const n of notes) console.error(`  - ${n}`)
if (wanted) console.error(`  - package.json at ${packageRoot} declares effect@${wanted}, and no lockfile this script can read pins it`)
console.error("  - install dependencies, or read the `effect` range in the nearest package.json")
process.exit(1)
