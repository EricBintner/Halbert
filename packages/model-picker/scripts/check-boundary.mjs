// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors

/**
 * Guards the extraction contract.
 *
 * This package has to survive being lifted into another repository unchanged,
 * so anything that quietly ties it to one host — a dependency, a network call,
 * a stylesheet, a hard-coded class list — has to fail here rather than at the
 * moment somebody tries to move it.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(
  decodeURIComponent(new URL('.', import.meta.url).pathname),
  '..',
)
const SRC = path.join(ROOT, 'src')

const IMPORT = /\b(?:from|import|require)\b\s*\(?\s*['"]([^'"]+)['"]/g
const CLASS_ATTR = /className\s*=\s*"([^"]*)"/g

const alwaysAllowed = (spec) =>
  spec.startsWith('.') ||
  spec === 'react' ||
  spec === 'react-dom' ||
  spec.startsWith('react/')

const testOnlyAllowed = (spec) =>
  spec === 'vitest' ||
  spec.startsWith('vitest/') ||
  spec.startsWith('@testing-library/') ||
  spec.startsWith('react-dom/')

const FORBIDDEN = [
  [/\bfetch\s*\(/, 'performs its own I/O: fetch('],
  [/\bXMLHttpRequest\b/, 'performs its own I/O: XMLHttpRequest'],
  [/\bnew\s+WebSocket\b/, 'performs its own I/O: new WebSocket'],
  [/\baxios\b/, 'performs its own I/O: axios'],
  [/\bMath\.random\s*\(/, 'non-deterministic render: Math.random('],
  [/\bDate\.now\s*\(/, 'non-deterministic render: Date.now('],
]

function walk(dir) {
  const found = []
  for (const entry of readdirSync(dir).sort()) {
    const full = path.join(dir, entry)
    if (statSync(full).isDirectory()) found.push(...walk(full))
    else if (/\.tsx?$/.test(entry)) found.push(full)
  }
  return found
}

function inspect(file) {
  const rel = path.relative(ROOT, file)
  const isTest =
    /\.test\.tsx?$/.test(rel) || rel.split(path.sep).includes('test')
  const problems = []

  readFileSync(file, 'utf8')
    .split('\n')
    .forEach((line, index) => {
      const at = (reason) => problems.push(`${rel}:${index + 1}: ${reason}`)

      for (const [, spec] of line.matchAll(IMPORT)) {
        if (spec.endsWith('.css')) at(`stylesheet import: ${spec}`)
        else if (alwaysAllowed(spec)) continue
        else if (isTest && testOnlyAllowed(spec)) continue
        else at(`import from outside the package: ${spec}`)
      }

      for (const [, value] of line.matchAll(CLASS_ATTR)) {
        const words = value.trim().split(/\s+/).filter(Boolean)
        if (words.length > 1) at(`hard-coded class list: className="${value}"`)
      }

      if (/\bstyled\./.test(line)) at('styled-components usage')

      if (!isTest) {
        for (const [pattern, reason] of FORBIDDEN) {
          if (pattern.test(line)) at(reason)
        }
      }
    })

  return problems
}

let files
try {
  files = walk(SRC)
} catch {
  console.error(`check-boundary: no source directory at ${SRC}`)
  process.exit(2)
}

const problems = files.flatMap(inspect)

if (problems.length > 0) {
  for (const problem of problems) console.error(problem)
  const plural = problems.length === 1 ? '' : 's'
  console.error(
    `\n${problems.length} boundary violation${plural} across ${files.length} files.`,
  )
  process.exit(1)
}

console.log(`Boundary clean: ${files.length} source files, no violations.`)
