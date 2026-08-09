import { afterEach, describe, expect, test } from "bun:test"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { normalizeSettings } from "../src/config"
import { compareTranscripts, transcribeChunk } from "../src/providers"

const originalFetch = globalThis.fetch
const originalOpenAI = process.env.OPENAI_API_KEY
const originalGroq = process.env.GROQ_API_KEY
const root = join("/tmp", `transcribe-provider-${crypto.randomUUID()}`)
mkdirSync(root, { recursive: true })
const audio = join(root, "audio.mp3")
writeFileSync(audio, "test")
afterEach(() => { globalThis.fetch = originalFetch; process.env.OPENAI_API_KEY = originalOpenAI; process.env.GROQ_API_KEY = originalGroq })

describe("provider requests", () => {
  test("uses languages[] for gpt-transcribe", async () => {
    process.env.OPENAI_API_KEY = "test-key"
    let form: FormData | null = null
    globalThis.fetch = (async (_input: any, init: any) => { form = init.body; return new Response(JSON.stringify({ text: "hello", languages: [{ code: "en" }], usage: { total_tokens: 3 } }), { status: 200 }) }) as any
    const result = await transcribeChunk(audio, normalizeSettings({ provider: "openai", model: "gpt-transcribe", language: "en" }))
    expect(form!.get("languages[]")).toBe("en")
    expect(form!.get("language")).toBeNull()
    expect(result.text).toBe("hello")
  })

  test("uses diarized_json and automatic chunking", async () => {
    process.env.OPENAI_API_KEY = "test-key"
    let form: FormData | null = null
    globalThis.fetch = (async (_input: any, init: any) => { form = init.body; return new Response(JSON.stringify({ text: "hello", segments: [{ start: 0, end: 1, speaker: "A", text: "hello" }] }), { status: 200 }) }) as any
    const result = await transcribeChunk(audio, normalizeSettings({ provider: "openai", diarize: true }))
    expect(form!.get("response_format")).toBe("diarized_json")
    expect(form!.get("chunking_strategy")).toBe("auto")
    expect(result.segments[0]?.speaker).toBe("A")
  })

  test("comparison is ephemeral and uses gpt-5.6-luna", async () => {
    process.env.OPENAI_API_KEY = "test-key"
    let request: any
    globalThis.fetch = (async (_input: any, init: any) => { request = JSON.parse(init.body); return new Response(JSON.stringify({ output_text: "Winner: Transcript A" }), { status: 200 }) }) as any
    expect(await compareTranscripts("a.txt", "one", "b.txt", "two")).toContain("Transcript A")
    expect(request.model).toBe("gpt-5.6-luna")
  })
})

process.on("exit", () => rmSync(root, { recursive: true, force: true }))
