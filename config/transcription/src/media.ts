import { createHash } from "node:crypto"
import { existsSync, mkdirSync, statSync } from "node:fs"
import { basename, join, resolve } from "node:path"
import { command } from "./process"
import { expandUserPath } from "./paths"
import type { Settings, SourceKind } from "./types"

export interface InputInfo { kind: SourceKind, locator: string, title: string, fingerprint: string | null, playlistId?: string }
export interface PlaylistEntry { position: number, locator: string, title: string, videoId: string }

export async function inspectInput(input: string): Promise<InputInfo> {
  if (!/^https?:\/\//i.test(input)) {
    const locator = resolve(expandUserPath(input))
    if (!existsSync(locator)) throw new Error(`Media file not found: ${locator}`)
    const stat = statSync(locator)
    const fingerprint = createHash("sha256").update(`${locator}\0${stat.size}\0${stat.mtimeMs}`).digest("hex")
    return { kind: "local", locator, title: basename(locator), fingerprint }
  }
  const json = JSON.parse(await command(["yt-dlp", "--flat-playlist", "--dump-single-json", "--no-warnings", input], { quiet: true }))
  const playlist = Array.isArray(json.entries) && json.entries.length > 0
  return { kind: playlist ? "playlist" : "youtube", locator: input, title: String(json.title || json.fulltitle || json.id || input), fingerprint: json.id ? String(json.id) : null, playlistId: playlist ? String(json.id || "") : undefined }
}

export async function playlistEntries(input: string): Promise<{ title: string, id: string, entries: PlaylistEntry[] }> {
  const json = JSON.parse(await command(["yt-dlp", "--flat-playlist", "--dump-single-json", "--no-warnings", input], { quiet: true }))
  if (!Array.isArray(json.entries)) throw new Error("The URL is not a playlist.")
  return {
    title: String(json.title || json.id || "Playlist"),
    id: String(json.id || createHash("sha256").update(input).digest("hex").slice(0, 12)),
    entries: json.entries.filter((entry: any) => entry?.id).map((entry: any, position: number) => ({
      position,
      videoId: String(entry.id),
      locator: /^https?:\/\//.test(String(entry.url || "")) ? String(entry.url) : `https://www.youtube.com/watch?v=${entry.id}`,
      title: String(entry.title || entry.id),
    })),
  }
}

export async function durationSeconds(path: string): Promise<number> {
  const output = await command(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path], { quiet: true })
  const duration = Number(output.trim())
  if (!Number.isFinite(duration) || duration <= 0) throw new Error(`Could not determine media duration: ${path}`)
  return duration
}

export async function prepareAudio(locator: string, kind: SourceKind, cacheDirectory: string): Promise<string> {
  mkdirSync(cacheDirectory, { recursive: true, mode: 0o700 })
  const target = join(cacheDirectory, "source.mp3")
  if (existsSync(target) && statSync(target).size > 0) return target
  let source = locator
  if (kind !== "local") {
    const downloaded = join(cacheDirectory, "download.%(ext)s")
    await command(["yt-dlp", "--no-playlist", "-f", "bestaudio/best", "-o", downloaded, locator])
    const candidates = Array.from(new Bun.Glob("download.*").scanSync({ cwd: cacheDirectory, absolute: true }))
    if (!candidates[0]) throw new Error("yt-dlp completed without producing an audio file.")
    source = candidates[0]
  }
  await command(["ffmpeg", "-v", "error", "-y", "-i", source, "-vn", "-map_metadata", "-1", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", target])
  return target
}

export interface ChunkPlan { position: number, startSeconds: number, durationSeconds: number, path: string, status: "pending" }

export async function createChunks(audio: string, directory: string, settings: Settings): Promise<ChunkPlan[]> {
  mkdirSync(directory, { recursive: true, mode: 0o700 })
  const total = await durationSeconds(audio)
  const step = settings.chunkSeconds - settings.chunkOverlapSeconds
  const chunks: ChunkPlan[] = []
  for (let start = 0, position = 0; start < total; start += step, position++) {
    const duration = Math.min(settings.chunkSeconds, total - start)
    const path = join(directory, `chunk-${String(position + 1).padStart(5, "0")}.mp3`)
    if (!existsSync(path)) await command(["ffmpeg", "-v", "error", "-y", "-ss", String(start), "-t", String(duration), "-i", audio, "-vn", "-map_metadata", "-1", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", path])
    if (statSync(path).size > settings.maxUploadMb * 1024 * 1024) throw new Error(`Chunk ${position + 1} exceeds ${settings.maxUploadMb} MB; reduce chunk seconds.`)
    chunks.push({ position, startSeconds: start, durationSeconds: duration, path, status: "pending" })
  }
  return chunks
}

export async function downloadYoutubeSubtitles(url: string, directory: string): Promise<string> {
  mkdirSync(directory, { recursive: true, mode: 0o700 })
  const template = join(directory, "subtitle")
  await command(["yt-dlp", "--no-playlist", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "en.*,en", "--sub-format", "vtt", "-o", template, url])
  const candidates = Array.from(new Bun.Glob("subtitle*.vtt").scanSync({ cwd: directory, absolute: true }))
  if (!candidates[0]) throw new Error("No English YouTube subtitles were available.")
  const content = await Bun.file(candidates[0]).text()
  const text = content.split(/\r?\n/)
    .filter((line) => line && !line.startsWith("WEBVTT") && !line.includes("-->") && !/^\d+$/.test(line) && !line.startsWith("NOTE"))
    .map((line) => line.replace(/<[^>]+>/g, "").trim())
    .filter((line, index, lines) => line && line !== lines[index - 1])
    .join("\n")
  return text.trim()
}
