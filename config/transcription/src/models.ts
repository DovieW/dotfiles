import type { Provider, Settings } from "./types"

export interface ModelCapability {
  provider: Provider
  id: string
  label: string
  diarization: boolean
  prompt: boolean
  timestamps: boolean
  languageField: "language" | "languages" | "none"
  default?: boolean
}

export const MODELS: ModelCapability[] = [
  { provider: "openai", id: "gpt-transcribe", label: "GPT Transcribe", diarization: false, prompt: true, timestamps: false, languageField: "languages", default: true },
  { provider: "openai", id: "gpt-4o-transcribe", label: "GPT-4o Transcribe", diarization: false, prompt: true, timestamps: false, languageField: "language" },
  { provider: "openai", id: "gpt-4o-mini-transcribe", label: "GPT-4o mini Transcribe", diarization: false, prompt: true, timestamps: false, languageField: "language" },
  { provider: "openai", id: "whisper-1", label: "Whisper 1", diarization: false, prompt: true, timestamps: true, languageField: "language" },
  { provider: "openai", id: "gpt-4o-transcribe-diarize", label: "GPT-4o Transcribe Diarize", diarization: true, prompt: false, timestamps: true, languageField: "none" },
  { provider: "groq", id: "whisper-large-v3-turbo", label: "Whisper Large v3 Turbo", diarization: false, prompt: true, timestamps: true, languageField: "language", default: true },
  { provider: "groq", id: "whisper-large-v3", label: "Whisper Large v3", diarization: false, prompt: true, timestamps: true, languageField: "language" },
  { provider: "fireworks", id: "whisper-v3-turbo", label: "Whisper v3 Turbo", diarization: false, prompt: true, timestamps: true, languageField: "language", default: true },
  { provider: "fireworks", id: "whisper-v3", label: "Whisper v3", diarization: false, prompt: true, timestamps: true, languageField: "language" },
  { provider: "youtube-transcript", id: "youtube", label: "YouTube subtitles", diarization: false, prompt: false, timestamps: false, languageField: "none", default: true },
]

export function modelsFor(provider: Provider): ModelCapability[] {
  return MODELS.filter((model) => model.provider === provider)
}

export function effectiveModel(settings: Settings): ModelCapability {
  const id = settings.diarize ? "gpt-4o-transcribe-diarize" : settings.model
  const model = MODELS.find((candidate) => candidate.provider === settings.provider && candidate.id === id)
  if (!model) throw new Error(`Unsupported ${settings.provider} model: ${id}`)
  return model
}

export function validateSettings(settings: Settings): string[] {
  const errors: string[] = []
  if (settings.diarize && settings.provider !== "openai") errors.push("Diarization requires OpenAI.")
  try { effectiveModel(settings) } catch (error) { errors.push((error as Error).message) }
  for (const [name, value, minimum] of [
    ["chunk seconds", settings.chunkSeconds, 10],
    ["chunk concurrency", settings.chunkConcurrency, 1],
    ["maximum upload MB", settings.maxUploadMb, 1],
    ["maximum retries", settings.maxRetries, 0],
    ["initial retry seconds", settings.initialRetrySeconds, 1],
  ] as const) if (!Number.isFinite(value) || value < minimum) errors.push(`${name} must be at least ${minimum}.`)
  if (settings.chunkOverlapSeconds < 0 || settings.chunkOverlapSeconds >= settings.chunkSeconds) errors.push("Chunk overlap must be non-negative and shorter than the chunk.")
  if (!settings.language.trim()) errors.push("Language cannot be blank.")
  return errors
}
