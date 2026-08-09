export type Provider = "groq" | "openai" | "fireworks" | "youtube-transcript"
export type SourceKind = "local" | "youtube" | "playlist"
export type RunStatus =
  | "draft"
  | "preparing"
  | "transcribing"
  | "pausing"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"
  | "deleting"

export interface Settings {
  schemaVersion: 2
  provider: Provider
  model: string
  language: string
  diarize: boolean
  cleanup: boolean
  prompt: string
  keywords: string[]
  chunkSeconds: number
  chunkOverlapSeconds: number
  continuityChars: number
  chunkConcurrency: number
  maxUploadMb: number
  maxRetries: number
  initialRetrySeconds: number
  keepAudio: boolean
  keepChunks: boolean
}

export interface SourceRecord {
  id: string
  kind: SourceKind
  locator: string
  title: string
  fingerprint: string | null
  createdAt: string
  updatedAt: string
}

export interface RunRecord {
  id: string
  sourceId: string
  name: string
  status: RunStatus
  provider: Provider
  model: string
  settings: Settings
  artifactDir: string
  error: string | null
  createdAt: string
  updatedAt: string
  completedAt: string | null
}

export interface Segment {
  start: number | null
  end: number | null
  speaker: string | null
  text: string
}

export interface TranscriptDocument {
  schemaVersion: 1
  runId: string
  source: Pick<SourceRecord, "id" | "kind" | "locator" | "title">
  provider: Provider
  model: string
  language: string
  text: string
  segments: Segment[]
  usage: Record<string, unknown>
  createdAt: string
}

export interface ChunkRecord {
  id: number
  runId: string
  position: number
  startSeconds: number
  durationSeconds: number
  status: "pending" | "active" | "completed" | "failed"
  path: string
  text: string | null
  responseJson: string | null
  attempts: number
  error: string | null
}
