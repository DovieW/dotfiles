import type { RunRecord, TranscriptDocument } from "./types"

export interface TextMatch { index: number, line: number, column: number }

export function formatTimestamp(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "--:--"
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remainder = total % 60
  return hours
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
}

export function formatTranscript(document: TranscriptDocument): string {
  if (!document.segments.length) return document.text
  return document.segments.map((segment) => {
    const speaker = segment.speaker ? ` ${segment.speaker}` : ""
    return `[${formatTimestamp(segment.start)}]${speaker}  ${segment.text}`
  }).join("\n")
}

export function findTextMatches(text: string, query: string): TextMatch[] {
  const needle = query.toLocaleLowerCase()
  if (!needle) return []
  const haystack = text.toLocaleLowerCase(), matches: TextMatch[] = []
  let from = 0
  while (from <= haystack.length - needle.length) {
    const index = haystack.indexOf(needle, from)
    if (index < 0) break
    const prefix = text.slice(0, index), lastBreak = prefix.lastIndexOf("\n")
    matches.push({ index, line: prefix.split("\n").length - 1, column: index - lastBreak - 1 })
    from = index + Math.max(needle.length, 1)
  }
  return matches
}

export function viewerMetadata(run: RunRecord | null, document: TranscriptDocument | null): string {
  if (!run && !document) return "Text result"
  const provider = run?.provider || document?.provider
  const model = run?.model || document?.model
  const language = run?.settings.language || document?.language
  const completed = run?.completedAt ? new Date(run.completedAt).toLocaleString() : document?.createdAt ? new Date(document.createdAt).toLocaleString() : ""
  return [provider && model ? `${provider}/${model}` : provider || model, language, completed].filter(Boolean).join(" · ")
}
