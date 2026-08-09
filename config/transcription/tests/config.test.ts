import { describe, expect, test } from "bun:test"
import { normalizeSettings } from "../src/config"
import { effectiveModel, modelsFor, validateSettings } from "../src/models"

describe("settings and model capabilities", () => {
  test("migrates legacy snake-case settings", () => {
    const settings = normalizeSettings({ provider: "openai", model: "gpt-transcribe", chunk_seconds: 200, chunk_overlap_seconds: 2, chunk_concurrency: 2 })
    expect(settings.schemaVersion).toBe(2)
    expect(settings.model).toBe("gpt-transcribe")
    expect(settings.chunkSeconds).toBe(200)
    expect(settings.chunkOverlapSeconds).toBe(2)
    expect(settings.chunkConcurrency).toBe(2)
  })

  test("contains every promised OpenAI and Groq model", () => {
    expect(modelsFor("openai").map((model) => model.id)).toEqual([
      "gpt-transcribe", "gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1", "gpt-4o-transcribe-diarize",
    ])
    expect(modelsFor("groq").map((model) => model.id)).toEqual(["whisper-large-v3-turbo", "whisper-large-v3"])
  })

  test("diarization is a first-class specialized model", () => {
    const settings = normalizeSettings({ provider: "openai", diarize: true })
    expect(effectiveModel(settings).id).toBe("gpt-4o-transcribe-diarize")
    expect(effectiveModel(settings).diarization).toBeTrue()
  })

  test("rejects unsafe chunk settings", () => {
    const settings = normalizeSettings({ chunk_seconds: 20, chunk_overlap_seconds: 20 })
    expect(validateSettings(settings)).toContain("Chunk overlap must be non-negative and shorter than the chunk.")
  })
})
