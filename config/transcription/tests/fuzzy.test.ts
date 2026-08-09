import { describe, expect, test } from "bun:test"
import { fuzzyOptions, fuzzyScore } from "../src/fuzzy"

describe("fuzzy matching", () => {
  test("matches subsequences and ranks exact text first", () => {
    expect(fuzzyScore("gpttr", "gpt-transcribe")).not.toBeNull()
    const results = fuzzyOptions("gpt transcribe", [
      { name: "Groq", description: "whisper-large-v3" },
      { name: "GPT Transcribe", description: "OpenAI transcription" },
      { name: "GPT Mini", description: "gpt-4o-mini-transcribe" },
    ])
    expect(results[0]?.name).toBe("GPT Transcribe")
    expect(results.map((item) => item.name)).not.toContain("Groq")
  })

  test("searches descriptions as well as labels", () => {
    const results = fuzzyOptions("speaker labels", [
      { name: "Diarize", description: "automatic speaker labels" },
      { name: "Plain", description: "unlabelled text" },
    ])
    expect(results.map((item) => item.name)).toEqual(["Diarize"])
  })
})
