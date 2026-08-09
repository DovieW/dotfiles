import { readdirSync, statSync } from "node:fs"
import { basename, dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path"
import { fuzzyScore } from "./fuzzy"

export interface PathSuggestion { name: string, description: string, path: string, directory: boolean }

export function expandUserPath(value: string): string {
  if (value === "~") return process.env.HOME || value
  if (value.startsWith(`~${sep}`)) return join(process.env.HOME || "~", value.slice(2))
  return value
}

function displayPath(path: string, original: string): string {
  const home = process.env.HOME
  if (original.startsWith("~") && home && (path === home || path.startsWith(`${home}${sep}`))) return `~${path.slice(home.length)}`
  if (!isAbsolute(original)) {
    const result = relative(process.cwd(), path)
    return result || "."
  }
  return path
}

export function pathSuggestions(value: string, extensions: string[] = [], limit = 100): PathSuggestion[] {
  const trimmed = value.trim()
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed)) return []
  const expanded = expandUserPath(trimmed || ".")
  let directory: string, query: string
  try {
    if (trimmed.endsWith(sep) || statSync(resolve(expanded)).isDirectory()) { directory = resolve(expanded); query = "" }
    else { directory = resolve(dirname(expanded)); query = basename(expanded) }
  } catch { directory = resolve(dirname(expanded)); query = basename(expanded) }

  const wanted = new Set(extensions.map((extension) => extension.toLocaleLowerCase()))
  let entries
  try { entries = readdirSync(directory, { withFileTypes: true }) } catch { return [] }
  return entries.filter((entry) => entry.isDirectory() || !wanted.size || wanted.has(extname(entry.name).toLocaleLowerCase()))
    .map((entry, index) => ({ entry, index, score: query ? fuzzyScore(query, entry.name) : 0 }))
    .filter((item) => item.score !== null)
    .sort((left, right) => Number(right.entry.isDirectory()) - Number(left.entry.isDirectory()) || right.score! - left.score! || left.index - right.index)
    .slice(0, limit)
    .map(({ entry }) => {
      const absolute = join(directory, entry.name)
      const path = `${displayPath(absolute, trimmed)}${entry.isDirectory() ? sep : ""}`
      return { name: path, description: entry.isDirectory() ? "directory" : "file", path, directory: entry.isDirectory() }
    })
}
