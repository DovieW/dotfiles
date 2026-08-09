import { describe, expect, test } from "bun:test"
import { findTextMatches, formatTimestamp, formatTranscript } from "../src/viewer"

describe("transcript viewer helpers", () => {
  test("formats timestamps and speaker-labelled segments", () => {
    expect(formatTimestamp(65.9)).toBe("01:05")
    expect(formatTimestamp(3661)).toBe("01:01:01")
    expect(formatTranscript({
      schemaVersion: 1, runId: "run", source: { id: "source", kind: "local", locator: "/tmp/a.m4a", title: "a" },
      provider: "openai", model: "gpt-4o-transcribe-diarize", language: "en", text: "Hello there.", usage: {}, createdAt: new Date(0).toISOString(),
      segments: [{ start: 5, end: 7, speaker: "Speaker 1", text: "Hello there." }],
    })).toBe("[00:05] Speaker 1  Hello there.")
  })

  test("finds case-insensitive matches with line positions", () => {
    expect(findTextMatches("Alpha beta\nalpha again", "ALPHA")).toEqual([
      { index: 0, line: 0, column: 0 },
      { index: 11, line: 1, column: 0 },
    ])
  })
})
