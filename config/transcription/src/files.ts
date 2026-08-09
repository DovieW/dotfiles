import { readdirSync } from "node:fs"
import { basename, dirname, extname, join, resolve } from "node:path"

const ignored = new Set([".git", ".cache", ".local", "node_modules", "target", "dist", "build"])

export interface FileChoice { name: string, description: string, path: string }

export function defaultSearchRoots(): string[] {
  const home = process.env.HOME || "."
  return [process.cwd(), "Downloads", "Desktop", "Documents", "Music", "Videos"].map((entry) => entry === process.cwd() ? entry : join(home, entry))
}

export function discoverFiles(extensions: string[], roots = defaultSearchRoots(), limit = 5000): FileChoice[] {
  const wanted = new Set(extensions.map((extension) => extension.toLocaleLowerCase()))
  const found = new Map<string, FileChoice>()
  const walk = (directory: string, depth: number) => {
    if (depth > 6 || found.size >= limit) return
    let entries
    try { entries = readdirSync(directory, { withFileTypes: true }) } catch { return }
    for (const entry of entries) {
      if (found.size >= limit) break
      const path = resolve(directory, entry.name)
      if (entry.isDirectory()) {
        if (!ignored.has(entry.name) && !entry.name.startsWith(".")) walk(path, depth + 1)
      } else if (entry.isFile() && wanted.has(extname(entry.name).toLocaleLowerCase())) {
        found.set(path, { name: basename(path), description: dirname(path), path })
      }
    }
  }
  for (const root of [...new Set(roots.map((path) => resolve(path)))]) walk(root, 0)
  return [...found.values()].sort((left, right) => left.name.localeCompare(right.name) || left.path.localeCompare(right.path))
}

export const MEDIA_EXTENSIONS = [".aac", ".aiff", ".alac", ".flac", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".oga", ".ogg", ".opus", ".wav", ".webm", ".wma"]
export const TEXT_EXTENSIONS = [".txt", ".md", ".text"]
