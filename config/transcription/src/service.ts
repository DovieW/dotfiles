import { basename } from "node:path"
import { loadSettings, saveSettings } from "./config"
import { JobRunner, type JobEvent } from "./job"
import { inspectInput, playlistEntries } from "./media"
import { Library } from "./storage"
import type { RunRecord, Settings } from "./types"

export function nextAvailableRunName(desired: string, existing: string[]): string {
  const names = new Set(existing)
  if (!names.has(desired)) return desired
  for (let suffix = 2; ; suffix++) {
    const candidate = `${desired} (${suffix})`
    if (!names.has(candidate)) return candidate
  }
}

export async function createRuns(library: Library, input: string, name: string | undefined, settings: Settings, uniqueName = false): Promise<RunRecord[]> {
  const info = await inspectInput(input)
  saveSettings(settings)
  if (info.kind !== "playlist") {
    const source = library.sourceFor(info.kind, info.locator, info.title, info.fingerprint)
    let suggested = name || `${source.title.replace(/\.[^.]+$/, "")} — ${settings.model || settings.provider}`
    if (uniqueName) suggested = nextAvailableRunName(suggested, library.listRunsForSource(source.id).map((run) => run.name))
    return [library.createRun(source, suggested, settings)]
  }
  const playlist = await playlistEntries(input)
  const playlistSource = library.sourceFor("playlist", input, playlist.title, playlist.id)
  const sources = playlist.entries.map((entry) => library.sourceFor("youtube", entry.locator, entry.title, entry.videoId))
  library.createPlaylist(playlistSource, playlist.title, sources)
  return sources.map((source, index) => {
    let desired = `${name ? `${name} — ` : ""}${String(index + 1).padStart(3, "0")} — ${source.title}`
    if (uniqueName) desired = nextAvailableRunName(desired, library.listRunsForSource(source.id).map((run) => run.name))
    return library.createRun(source, desired, settings)
  })
}

export async function createAndRun(library: Library, input: string, name: string | undefined, settings = loadSettings(), notify?: (event: JobEvent) => void): Promise<RunRecord[]> {
  const runs = await createRuns(library, input, name, settings)
  const runner = new JobRunner(library, notify)
  const results: RunRecord[] = []
  for (const run of runs) results.push(await runner.run(run.id))
  return results
}

export function suggestedRunName(input: string, settings: Settings): string {
  return `${basename(input).replace(/\.[^.]+$/, "")} — ${settings.diarize ? "gpt-4o-transcribe-diarize" : settings.model}`
}
