import { existsSync, mkdirSync, rmSync } from "node:fs"
import { join } from "node:path"
import { createChunks, downloadYoutubeSubtitles, prepareAudio } from "./media"
import { cleanupTranscript, transcribeChunk } from "./providers"
import { Library } from "./storage"
import type { RunRecord, Segment, TranscriptDocument } from "./types"

export interface JobEvent {
  type: "status" | "chunk" | "retry" | "done" | "error"
  message: string
  completed?: number
  total?: number
}

export class JobRunner {
  private pauseRequested = false
  private forceRequested = false
  constructor(private library: Library, private notify: (event: JobEvent) => void = () => {}) {}

  requestPause(force = false): void {
    this.pauseRequested = true
    this.forceRequested ||= force
  }

  async restart(reference: string): Promise<RunRecord> {
    const run = this.library.requireRun(reference)
    this.library.db.run("DELETE FROM chunks WHERE run_id = ?", [run.id])
    for (const name of ["transcript.txt", "transcript.json"]) rmSync(join(run.artifactDir, name), { force: true })
    this.library.updateRun(run.id, { status: "draft", error: null, completedAt: null })
    return this.run(run.id)
  }

  async run(reference: string): Promise<RunRecord> {
    let run = this.library.requireRun(reference)
    const source = this.library.requireSource(run.sourceId)
    this.pauseRequested = false
    this.forceRequested = false
    const signal = () => this.requestPause()
    const forceSignal = () => this.requestPause(true)
    process.once("SIGINT", signal)
    process.once("SIGTERM", forceSignal)
    try {
      run = this.library.updateRun(run.id, { status: "preparing", error: null })
      this.notify({ type: "status", message: `Preparing ${source.title}` })
      if (run.provider === "youtube-transcript") return await this.runSubtitles(run)
      const cache = join(this.library.root, "sources", source.id, "cache")
      const audio = await prepareAudio(source.locator, source.kind, cache)
      let chunks = this.library.listChunks(run.id)
      if (!chunks.length) {
        const plan = await createChunks(audio, join(run.artifactDir, "chunks"), run.settings)
        this.library.setChunks(run.id, plan)
        chunks = this.library.listChunks(run.id)
      }
      run = this.library.updateRun(run.id, { status: "transcribing" })
      const pending = chunks.filter((chunk) => chunk.status !== "completed")
      const concurrency = run.settings.continuityChars > 0 ? 1 : Math.max(1, run.settings.chunkConcurrency)
      let next = 0, stopScheduling = false
      const worker = async () => {
        while (next < pending.length && !this.pauseRequested && !stopScheduling) {
          const chunk = pending[next++]!
          this.library.updateChunk(chunk.id, { status: "active", attempts: chunk.attempts + 1, error: null })
          const preceding = this.library.listChunks(run.id).filter((candidate) => candidate.position < chunk.position && candidate.text).at(-1)
          const continuity = preceding?.text?.slice(-run.settings.continuityChars) || ""
          this.notify({ type: "chunk", message: `Transcribing chunk ${chunk.position + 1}/${chunks.length}`, completed: this.library.listChunks(run.id).filter((candidate) => candidate.status === "completed").length, total: chunks.length })
          try {
            const result = await transcribeChunk(chunk.path, run.settings, continuity, (message) => this.notify({ type: "retry", message }))
            this.library.updateChunk(chunk.id, { status: "completed", text: result.text, responseJson: JSON.stringify(result.raw), error: null })
          } catch (error) {
            const message = (error as Error).message
            this.library.updateChunk(chunk.id, { status: "failed", error: message })
            stopScheduling = true
            throw error
          }
        }
      }
      const outcomes = await Promise.allSettled(Array.from({ length: Math.min(concurrency, pending.length || 1) }, () => worker()))
      const failure = outcomes.find((outcome): outcome is PromiseRejectedResult => outcome.status === "rejected")
      if (failure) throw failure.reason
      if (this.pauseRequested) {
        run = this.library.updateRun(run.id, { status: "paused", error: this.forceRequested ? "Interrupted" : null })
        this.notify({ type: "status", message: "Paused safely; run again to resume." })
        return run
      }
      const completed = this.library.listChunks(run.id)
      if (completed.some((chunk) => chunk.status !== "completed")) throw new Error("Not all chunks completed.")
      const segments: Segment[] = []
      const usage: Record<string, number> = {}
      for (const chunk of completed) {
        let raw: any = {}
        try { raw = JSON.parse(chunk.responseJson || "{}") } catch {}
        for (const segment of raw.segments || []) segments.push({ start: Number.isFinite(segment.start) ? segment.start + chunk.startSeconds : null, end: Number.isFinite(segment.end) ? segment.end + chunk.startSeconds : null, speaker: segment.speaker == null ? null : String(segment.speaker), text: String(segment.text || "").trim() })
        for (const [key, value] of Object.entries(raw.usage || {})) if (typeof value === "number") usage[key] = (usage[key] || 0) + value
      }
      const text = completed.map((chunk) => chunk.text?.trim()).filter(Boolean).join("\n\n")
      const document: TranscriptDocument = { schemaVersion: 1, runId: run.id, source: { id: source.id, kind: source.kind, locator: source.locator, title: source.title }, provider: run.provider, model: run.settings.diarize ? "gpt-4o-transcribe-diarize" : run.model, language: run.settings.language, text, segments, usage, createdAt: new Date().toISOString() }
      this.library.writeTranscript(run, document)
      if (!run.settings.keepChunks) rmSync(join(run.artifactDir, "chunks"), { recursive: true, force: true })
      run = this.library.updateRun(run.id, { status: "completed", completedAt: new Date().toISOString() })
      this.notify({ type: "done", message: `Transcript written to ${join(run.artifactDir, "transcript.txt")}`, completed: chunks.length, total: chunks.length })
      return run
    } catch (error) {
      const message = (error as Error).message
      run = this.library.updateRun(run.id, { status: this.pauseRequested ? "paused" : "failed", error: message })
      this.notify({ type: "error", message })
      throw error
    } finally {
      process.off("SIGINT", signal)
      process.off("SIGTERM", forceSignal)
    }
  }

  private async runSubtitles(run: RunRecord): Promise<RunRecord> {
    const source = this.library.requireSource(run.sourceId)
    if (source.kind === "local" || source.kind === "playlist") throw new Error("YouTube subtitle mode requires a video URL.")
    mkdirSync(run.artifactDir, { recursive: true, mode: 0o700 })
    let text = await downloadYoutubeSubtitles(source.locator, join(run.artifactDir, "subtitles"))
    if (run.settings.cleanup) text = await cleanupTranscript(text, run.settings.prompt)
    const document: TranscriptDocument = { schemaVersion: 1, runId: run.id, source: { id: source.id, kind: source.kind, locator: source.locator, title: source.title }, provider: "youtube-transcript", model: run.settings.cleanup ? "gpt-5.4-nano" : "youtube", language: run.settings.language, text, segments: [], usage: {}, createdAt: new Date().toISOString() }
    this.library.writeTranscript(run, document)
    const completed = this.library.updateRun(run.id, { status: "completed", completedAt: new Date().toISOString() })
    this.notify({ type: "done", message: `Transcript written to ${join(run.artifactDir, "transcript.txt")}` })
    return completed
  }
}
