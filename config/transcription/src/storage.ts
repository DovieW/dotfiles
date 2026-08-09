import { Database } from "bun:sqlite"
import { createHash, randomUUID } from "node:crypto"
import { chmodSync, copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs"
import { basename, dirname, join, resolve } from "node:path"
import { normalizeSettings, stateRoot } from "./config"
import type { ChunkRecord, RunRecord, RunStatus, Settings, SourceKind, SourceRecord, TranscriptDocument } from "./types"

function now(): string { return new Date().toISOString() }
function id(prefix: string): string { return `${prefix}_${randomUUID()}` }
function legacyId(prefix: string, value: string): string { return `${prefix}_${createHash("sha256").update(value).digest("hex").slice(0, 24)}` }

export function atomicJson(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 })
  const temporary = `${path}.tmp-${process.pid}`
  writeFileSync(temporary, JSON.stringify(value, null, 2) + "\n", { mode: 0o600 })
  chmodSync(temporary, 0o600)
  renameSync(temporary, path)
}

export class Library {
  readonly root: string
  readonly db: Database

  constructor(root = stateRoot()) {
    this.root = root
    mkdirSync(root, { recursive: true, mode: 0o700 })
    if ((statSync(root).mode & 0o777) !== 0o700) chmodSync(root, 0o700)
    const databasePath = join(root, "library.sqlite3")
    this.db = new Database(databasePath, { create: true })
    if ((statSync(databasePath).mode & 0o777) !== 0o600) chmodSync(databasePath, 0o600)
    this.db.run("PRAGMA journal_mode = WAL")
    this.db.run("PRAGMA busy_timeout = 5000")
    this.db.run("PRAGMA foreign_keys = ON")
    this.migrateSchema()
  }

  close(): void { this.db.close() }

  private migrateSchema(): void {
    this.db.run(`CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)`)
    const version = Number((this.db.query("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").get() as {version: number}).version)
    if (version < 1) this.db.transaction(() => {
      this.db.run(`CREATE TABLE sources(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, locator TEXT NOT NULL, title TEXT NOT NULL,
        fingerprint TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(kind, locator)
      )`)
      this.db.run(`CREATE TABLE runs(
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        name TEXT NOT NULL, status TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
        settings_json TEXT NOT NULL, artifact_dir TEXT NOT NULL, error TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT,
        UNIQUE(source_id, name)
      )`)
      this.db.run(`CREATE TABLE chunks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, start_seconds REAL NOT NULL, duration_seconds REAL NOT NULL,
        status TEXT NOT NULL, path TEXT NOT NULL, text TEXT, response_json TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, error TEXT, UNIQUE(run_id, position)
      )`)
      this.db.run(`CREATE TABLE playlists(
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        title TEXT NOT NULL, created_at TEXT NOT NULL
      )`)
      this.db.run(`CREATE TABLE playlist_items(
        playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
        position INTEGER NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        PRIMARY KEY(playlist_id, position)
      )`)
      this.db.run("INSERT INTO schema_migrations(version, applied_at) VALUES(1, ?)", [now()])
    })()
  }

  sourceById(reference: string): SourceRecord | null {
    const rows = this.db.query("SELECT * FROM sources WHERE id = ? OR id LIKE ? ORDER BY id LIMIT 2").all(reference, `${reference}%`) as any[]
    if (rows.length > 1) throw new Error(`Ambiguous source reference: ${reference}`)
    return rows[0] ? this.mapSource(rows[0]) : null
  }

  sourceFor(kind: SourceKind, locator: string, title?: string, fingerprint?: string | null): SourceRecord {
    const canonical = kind === "local" ? resolve(locator) : locator
    const existing = this.db.query("SELECT * FROM sources WHERE kind = ? AND locator = ?").get(kind, canonical) as any
    if (existing) {
      const changedMedia = Boolean(fingerprint && existing.fingerprint && fingerprint !== existing.fingerprint)
      if ((title && title !== existing.title) || changedMedia) this.db.run("UPDATE sources SET title = ?, fingerprint = ?, updated_at = ? WHERE id = ?", [title || existing.title, fingerprint ?? existing.fingerprint, now(), existing.id])
      if (changedMedia) rmSync(join(this.root, "sources", existing.id, "cache"), { recursive: true, force: true })
      const source = this.sourceById(existing.id)!
      atomicJson(join(this.root, "sources", source.id, "source.json"), { schemaVersion: 1, ...source })
      return source
    }
    const timestamp = now()
    const source: SourceRecord = { id: id("src"), kind, locator: canonical, title: title || basename(canonical), fingerprint: fingerprint ?? null, createdAt: timestamp, updatedAt: timestamp }
    this.db.run("INSERT INTO sources VALUES(?, ?, ?, ?, ?, ?, ?)", [source.id, source.kind, source.locator, source.title, source.fingerprint, timestamp, timestamp])
    const directory = join(this.root, "sources", source.id)
    mkdirSync(directory, { recursive: true, mode: 0o700 })
    atomicJson(join(directory, "source.json"), { schemaVersion: 1, ...source })
    return source
  }

  listSources(): SourceRecord[] {
    return (this.db.query("SELECT * FROM sources ORDER BY updated_at DESC").all() as any[]).map((row) => this.mapSource(row))
  }

  createPlaylist(source: SourceRecord, title: string, entries: SourceRecord[]): string {
    const playlistId = id("playlist")
    this.db.transaction(() => {
      this.db.run("INSERT INTO playlists VALUES(?, ?, ?, ?)", [playlistId, source.id, title, now()])
      entries.forEach((entry, position) => this.db.run("INSERT INTO playlist_items VALUES(?, ?, ?)", [playlistId, position, entry.id]))
    })()
    return playlistId
  }

  listRuns(sourceId?: string): RunRecord[] {
    const rows = sourceId
      ? this.db.query("SELECT * FROM runs WHERE source_id = ? ORDER BY updated_at DESC").all(sourceId)
      : this.db.query("SELECT * FROM runs ORDER BY updated_at DESC").all()
    return (rows as any[]).map((row) => this.mapRun(row))
  }

  listRunsForSource(sourceId: string): RunRecord[] {
    const source = this.requireSource(sourceId)
    if (source.kind !== "playlist") return this.listRuns(sourceId)
    return (this.db.query(`SELECT runs.* FROM playlists
      JOIN playlist_items ON playlist_items.playlist_id = playlists.id
      JOIN runs ON runs.source_id = playlist_items.source_id
      WHERE playlists.source_id = ?
      ORDER BY playlist_items.position, runs.updated_at DESC`).all(sourceId) as any[]).map((row) => this.mapRun(row))
  }

  runByReference(reference: string): RunRecord | null {
    let rows = this.db.query("SELECT * FROM runs WHERE id = ? OR id LIKE ? ORDER BY id LIMIT 3").all(reference, `${reference}%`) as any[]
    if (!rows.length) rows = this.db.query("SELECT * FROM runs WHERE name = ? ORDER BY updated_at DESC LIMIT 3").all(reference) as any[]
    if (rows.length > 1) throw new Error(`Ambiguous run reference: ${reference}; use a UUID prefix.`)
    return rows[0] ? this.mapRun(rows[0]) : null
  }

  createRun(source: SourceRecord, name: string, settings: Settings): RunRecord {
    const cleanName = name.trim()
    if (!cleanName) throw new Error("Run name cannot be blank.")
    if (this.db.query("SELECT 1 FROM runs WHERE source_id = ? AND name = ?").get(source.id, cleanName)) throw new Error(`A run named "${cleanName}" already exists for this source. Choose a different name or restart the existing run.`)
    const runId = id("run")
    const artifactDir = join(this.root, "sources", source.id, "runs", runId)
    mkdirSync(artifactDir, { recursive: true, mode: 0o700 })
    const timestamp = now()
    this.db.run(`INSERT INTO runs(id, source_id, name, status, provider, model, settings_json, artifact_dir, error, created_at, updated_at, completed_at)
      VALUES(?, ?, ?, 'draft', ?, ?, ?, ?, NULL, ?, ?, NULL)`, [runId, source.id, cleanName, settings.provider, settings.model, JSON.stringify(settings), artifactDir, timestamp, timestamp])
    const run = this.runByReference(runId)!
    this.writeRunManifest(run)
    return run
  }

  updateRun(id: string, values: { status?: RunStatus, error?: string | null, name?: string, completedAt?: string | null }): RunRecord {
    const run = this.runByReference(id)
    if (!run) throw new Error(`Run not found: ${id}`)
    if (values.name !== undefined) {
      const name = values.name.trim()
      if (!name) throw new Error("Run name cannot be blank.")
      if (this.db.query("SELECT 1 FROM runs WHERE source_id = ? AND name = ? AND id != ?").get(run.sourceId, name, run.id)) throw new Error(`A run named "${name}" already exists for this source.`)
      values.name = name
    }
    const updated = { ...run, ...values, updatedAt: now() }
    this.db.run("UPDATE runs SET name=?, status=?, error=?, updated_at=?, completed_at=? WHERE id=?", [updated.name, updated.status, updated.error, updated.updatedAt, updated.completedAt, run.id])
    const result = this.runByReference(run.id)!
    this.writeRunManifest(result)
    return result
  }

  duplicateRun(reference: string, name: string): RunRecord {
    const run = this.requireRun(reference)
    return this.createRun(this.sourceById(run.sourceId)!, name, run.settings)
  }

  deleteRun(reference: string): void {
    const run = this.requireRun(reference)
    this.updateRun(run.id, { status: "deleting" })
    try { rmSync(run.artifactDir, { recursive: true, force: true }) }
    catch (error) {
      this.updateRun(run.id, { status: "failed", error: `Deletion failed: ${(error as Error).message}` })
      throw error
    }
    this.db.transaction(() => this.db.run("DELETE FROM runs WHERE id = ?", [run.id]))()
  }

  requireRun(reference: string): RunRecord { const run = this.runByReference(reference); if (!run) throw new Error(`Run not found: ${reference}`); return run }
  requireSource(reference: string): SourceRecord { const source = this.sourceById(reference); if (!source) throw new Error(`Source not found: ${reference}`); return source }

  setChunks(runId: string, chunks: Omit<ChunkRecord, "id" | "runId" | "text" | "responseJson" | "attempts" | "error">[]): void {
    this.db.transaction(() => {
      this.db.run("DELETE FROM chunks WHERE run_id = ?", [runId])
      for (const chunk of chunks) this.db.run(`INSERT INTO chunks(run_id, position, start_seconds, duration_seconds, status, path, attempts)
        VALUES(?, ?, ?, ?, ?, ?, 0)`, [runId, chunk.position, chunk.startSeconds, chunk.durationSeconds, chunk.status, chunk.path])
    })()
  }

  listChunks(runId: string): ChunkRecord[] {
    return (this.db.query("SELECT * FROM chunks WHERE run_id = ? ORDER BY position").all(runId) as any[]).map((row) => ({
      id: row.id, runId: row.run_id, position: row.position, startSeconds: row.start_seconds, durationSeconds: row.duration_seconds,
      status: row.status, path: row.path, text: row.text, responseJson: row.response_json, attempts: row.attempts, error: row.error,
    }))
  }

  updateChunk(id: number, values: Partial<Pick<ChunkRecord, "status" | "text" | "responseJson" | "attempts" | "error">>): void {
    const current = this.db.query("SELECT * FROM chunks WHERE id = ?").get(id) as any
    if (!current) throw new Error(`Chunk not found: ${id}`)
    this.db.run("UPDATE chunks SET status=?, text=?, response_json=?, attempts=?, error=? WHERE id=?", [
      values.status ?? current.status, values.text ?? current.text, values.responseJson ?? current.response_json,
      values.attempts ?? current.attempts, values.error === undefined ? current.error : values.error, id,
    ])
  }

  writeTranscript(run: RunRecord, document: TranscriptDocument): void {
    atomicJson(join(run.artifactDir, "transcript.json"), document)
    const target = join(run.artifactDir, "transcript.txt")
    const temporary = `${target}.tmp-${process.pid}`
    writeFileSync(temporary, document.text.trimEnd() + "\n", { mode: 0o600 })
    renameSync(temporary, target)
  }

  exportRun(reference: string, format: "txt" | "json", output: string): string {
    const run = this.requireRun(reference)
    if (run.status !== "completed") throw new Error(`Run is ${run.status}, not completed.`)
    const source = join(run.artifactDir, `transcript.${format}`)
    if (!existsSync(source)) throw new Error(`Artifact is missing: ${source}`)
    const destination = resolve(output)
    mkdirSync(dirname(destination), { recursive: true })
    copyFileSync(source, destination)
    return destination
  }

  migrateLegacy(paths: string[] = []): { sources: number, runs: number } {
    const roots = paths.length ? paths.map((path) => resolve(path)) : [join(this.root, "sources")]
    let sourceCount = 0, runCount = 0
    for (const root of roots) {
      if (!existsSync(root)) continue
      const runFiles: string[] = []
      const walk = (directory: string, depth: number) => {
        if (depth > 5) return
        for (const entry of readdirSync(directory, { withFileTypes: true })) {
          const path = join(directory, entry.name)
          if (entry.isDirectory()) walk(path, depth + 1)
          else if (entry.name === "run.json") runFiles.push(path)
        }
      }
      if (statSync(root).isDirectory()) walk(root, 0)
      for (const runFile of runFiles) {
        let raw: any
        try { raw = JSON.parse(readFileSync(runFile, "utf8")) } catch { continue }
        if (!raw.source || !raw.provider) continue
        const locator = String(raw.source)
        const kind: SourceKind = /^https?:\/\//.test(locator) ? "youtube" : "local"
        const sourceId = legacyId("src", `${kind}:${kind === "local" ? resolve(locator) : locator}`)
        let source = this.sourceById(sourceId)
        if (!source) {
          const timestamp = now()
          source = { id: sourceId, kind, locator: kind === "local" ? resolve(locator) : locator, title: basename(locator), fingerprint: null, createdAt: timestamp, updatedAt: timestamp }
          this.db.run("INSERT OR IGNORE INTO sources VALUES(?, ?, ?, ?, NULL, ?, ?)", [source.id, source.kind, source.locator, source.title, timestamp, timestamp])
          atomicJson(join(this.root, "sources", source.id, "source.json"), { schemaVersion: 1, ...source })
          sourceCount++
        }
        const directory = dirname(runFile)
        const runId = legacyId("run", directory)
        if (this.runByReference(runId)) continue
        const settings = normalizeSettings(raw)
        const name = basename(directory)
        const completed = existsSync(join(directory, "transcript.txt.completed")) || existsSync(join(directory, "transcript.txt"))
        const timestamp = statSync(runFile).mtime.toISOString()
        this.db.run(`INSERT INTO runs VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)`, [
          runId, source.id, name, completed ? "completed" : "paused", settings.provider, settings.model,
          JSON.stringify(settings), directory, timestamp, timestamp, completed ? timestamp : null,
        ])
        const backup = join(directory, "run.legacy-v1.json")
        if (!existsSync(backup)) copyFileSync(runFile, backup)
        this.writeRunManifest(this.requireRun(runId))
        runCount++
      }
    }
    return { sources: sourceCount, runs: runCount }
  }

  rebuildFromManifests(): number {
    return this.migrateLegacy([join(this.root, "sources")]).runs
  }

  private writeRunManifest(run: RunRecord): void {
    atomicJson(join(run.artifactDir, "run.json"), { schemaVersion: 2, id: run.id, sourceId: run.sourceId, name: run.name, status: run.status, settings: run.settings, error: run.error, createdAt: run.createdAt, updatedAt: run.updatedAt, completedAt: run.completedAt })
  }

  private mapSource(row: any): SourceRecord { return { id: row.id, kind: row.kind, locator: row.locator, title: row.title, fingerprint: row.fingerprint, createdAt: row.created_at, updatedAt: row.updated_at } }
  private mapRun(row: any): RunRecord { return { id: row.id, sourceId: row.source_id, name: row.name, status: row.status, provider: row.provider, model: row.model, settings: normalizeSettings(JSON.parse(row.settings_json)), artifactDir: row.artifact_dir, error: row.error, createdAt: row.created_at, updatedAt: row.updated_at, completedAt: row.completed_at } }
}
