import { mkdirSync, readFileSync, renameSync, writeFileSync, chmodSync, existsSync } from "node:fs"
import { dirname, join } from "node:path"
import type { Settings } from "./types"
import { validateSettings } from "./models"

export const DEFAULT_SETTINGS: Settings = {
  schemaVersion: 2,
  provider: "groq",
  model: "whisper-large-v3-turbo",
  language: "en",
  diarize: false,
  cleanup: false,
  prompt: "",
  keywords: [],
  chunkSeconds: 900,
  chunkOverlapSeconds: 0,
  continuityChars: 0,
  chunkConcurrency: 1,
  maxUploadMb: 24,
  maxRetries: 10,
  initialRetrySeconds: 30,
  keepAudio: false,
  keepChunks: false,
}

export function xdgConfigHome(): string { return process.env.XDG_CONFIG_HOME || join(process.env.HOME || ".", ".config") }
export function xdgStateHome(): string { return process.env.XDG_STATE_HOME || join(process.env.HOME || ".", ".local", "state") }
export function configPath(): string { return join(xdgConfigHome(), "dotfiles", "transcribe", "config.json") }
export function legacyConfigPath(): string { return join(xdgConfigHome(), "dotfiles", "transcribe.json") }
export function stateRoot(): string { return join(xdgStateHome(), "dotfiles", "transcribe") }

function asNumber(value: unknown, fallback: number): number { const number = Number(value); return Number.isFinite(number) ? number : fallback }
function asBoolean(value: unknown, fallback: boolean): boolean { return value === undefined ? fallback : value === true || value === 1 || value === "1" }

export function normalizeSettings(raw: Record<string, unknown> = {}): Settings {
  const legacy = (camel: string, snake: string): unknown => raw[camel] ?? raw[snake]
  const provider = String(legacy("provider", "provider") ?? DEFAULT_SETTINGS.provider) as Settings["provider"]
  let model = String(legacy("model", "model") ?? "")
  if (!model) model = provider === "openai" ? "gpt-transcribe" : provider === "fireworks" ? "whisper-v3-turbo" : "whisper-large-v3-turbo"
  const settings: Settings = {
    schemaVersion: 2,
    provider,
    model,
    language: String(legacy("language", "language") ?? DEFAULT_SETTINGS.language),
    diarize: asBoolean(legacy("diarize", "diarize"), false),
    cleanup: asBoolean(legacy("cleanup", "cleanup"), false),
    prompt: String(legacy("prompt", "prompt") ?? ""),
    keywords: Array.isArray(raw.keywords) ? raw.keywords.map(String) : [],
    chunkSeconds: asNumber(legacy("chunkSeconds", "chunk_seconds"), DEFAULT_SETTINGS.chunkSeconds),
    chunkOverlapSeconds: asNumber(legacy("chunkOverlapSeconds", "chunk_overlap_seconds"), DEFAULT_SETTINGS.chunkOverlapSeconds),
    continuityChars: asNumber(legacy("continuityChars", "continuity_chars"), DEFAULT_SETTINGS.continuityChars),
    chunkConcurrency: asNumber(legacy("chunkConcurrency", "chunk_concurrency"), DEFAULT_SETTINGS.chunkConcurrency),
    maxUploadMb: asNumber(legacy("maxUploadMb", "max_upload_mb"), DEFAULT_SETTINGS.maxUploadMb),
    maxRetries: asNumber(legacy("maxRetries", "max_retries"), DEFAULT_SETTINGS.maxRetries),
    initialRetrySeconds: asNumber(legacy("initialRetrySeconds", "initial_retry_seconds"), DEFAULT_SETTINGS.initialRetrySeconds),
    keepAudio: asBoolean(legacy("keepAudio", "keep_audio"), false),
    keepChunks: asBoolean(legacy("keepChunks", "keep_chunks"), false),
  }
  if (settings.diarize) { settings.provider = "openai"; settings.model = "gpt-4o-transcribe-diarize" }
  return settings
}

export function loadSettings(): Settings {
  const target = existsSync(configPath()) ? configPath() : legacyConfigPath()
  if (!existsSync(target)) return { ...DEFAULT_SETTINGS }
  try {
    const settings = normalizeSettings(JSON.parse(readFileSync(target, "utf8")))
    if (target === legacyConfigPath() && !existsSync(configPath())) saveSettings(settings)
    return settings
  } catch { return { ...DEFAULT_SETTINGS } }
}

export function saveSettings(settings: Settings): void {
  const errors = validateSettings(settings)
  if (errors.length) throw new Error(errors.join(" "))
  const target = configPath()
  mkdirSync(dirname(target), { recursive: true, mode: 0o700 })
  const temporary = `${target}.tmp-${process.pid}`
  writeFileSync(temporary, JSON.stringify(settings, null, 2) + "\n", { mode: 0o600 })
  chmodSync(temporary, 0o600)
  renameSync(temporary, target)
}
