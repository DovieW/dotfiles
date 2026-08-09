import { afterEach, describe, expect, test } from "bun:test"
import { testRender } from "@opentui/solid"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { createTranscribeApp } from "../src/tui"
import { Library } from "../src/storage"

const roots: string[] = []
function temporary(): string {
  const path = join("/tmp", `transcribe-tui-test-${crypto.randomUUID()}`)
  mkdirSync(path, { recursive: true })
  roots.push(path)
  return path
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe("TUI navigation", () => {
  test("opens the library and a source without losing reactive state", async () => {
    const root = temporary()
    process.env.XDG_CONFIG_HOME = join(root, "config")
    const library = new Library(join(root, "state"))
    const source = library.sourceFor("local", "/tmp/example.m4a", "Example recording")
    const run = library.createRun(source, "first pass", {
      schemaVersion: 2, provider: "groq", model: "whisper-large-v3-turbo", language: "en",
      diarize: false, cleanup: false, prompt: "", keywords: [], chunkSeconds: 900,
      chunkOverlapSeconds: 0, continuityChars: 0, chunkConcurrency: 1, maxUploadMb: 24,
      maxRetries: 10, initialRetrySeconds: 30, keepAudio: false, keepChunks: false,
    })
    library.updateRun(run.id, { status: "completed", completedAt: new Date().toISOString() })
    writeFileSync(join(run.artifactDir, "transcript.txt"), "A transcript worth reading.\n")

    const App = createTranscribeApp(library)
    const setup = await testRender(() => <App />, { width: 90, height: 30 })
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("Quick Transcribe")
    await setup.mockInput.typeText("library")
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("Search › library")
    expect(setup.captureCharFrame()).toContain("Library")
    expect(setup.captureCharFrame()).not.toContain("New transcription")
    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("library · sources")
    expect(setup.captureCharFrame()).toContain("Example recording")

    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("library · Example recording")
    expect(setup.captureCharFrame()).toContain("first pass")

    await setup.mockInput.typeText("no-such-run")
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("No matches")
    setup.mockInput.pressEscape()
    await Bun.sleep(75)
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("first pass")
    expect(setup.captureCharFrame()).toContain("library · Example recording")

    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("View transcript")

    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("A transcript worth reading.")
    await setup.mockInput.typeText("worth")
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("Find › worth")
    expect(setup.captureCharFrame()).toContain("1/1")
    setup.mockInput.pressEscape()
    await Bun.sleep(75)
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("A transcript worth reading.")
    expect(setup.captureCharFrame()).toContain("type to search")
    setup.mockInput.pressEscape()
    await Bun.sleep(75)
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("View transcript")

    setup.mockInput.pressEscape()
    await Bun.sleep(75)
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("library · Example recording")
    setup.mockInput.pressEscape()
    await Bun.sleep(75)
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("library · sources")
    setup.mockInput.pressEscape()
    await Bun.sleep(75)
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("transcribe home")

    const mediaPath = join(root, "meeting-audio.m4a")
    writeFileSync(mediaPath, "audio")
    await setup.mockInput.typeText("new transcription")
    await setup.flush()
    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("new transcription · media")
    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("exact location")
    await setup.mockInput.typeText(join(root, "maud"))
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("meeting-audio.m4a")
    setup.mockInput.pressTab()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain(mediaPath)

    setup.renderer.destroy()
    library.close()
  })

  test("quick transcribe starts immediately and opens the completed transcript", async () => {
    const root = temporary(), mediaPath = join(root, "quick-meeting.m4a")
    process.env.XDG_CONFIG_HOME = join(root, "config")
    writeFileSync(mediaPath, "audio")
    const library = new Library(join(root, "state"))
    const finish = async (reference: string) => {
      const run = library.requireRun(reference), source = library.requireSource(run.sourceId)
      library.writeTranscript(run, {
        schemaVersion: 1, runId: run.id, source, provider: run.provider, model: run.model,
        language: run.settings.language, text: "Fast transcript output.", segments: [], usage: {}, createdAt: new Date().toISOString(),
      })
      return library.updateRun(run.id, { status: "completed", completedAt: new Date().toISOString() })
    }
    const App = createTranscribeApp(library, {
      requireCredential: () => "test-key",
      createRuns: async (target, input, name, settings) => {
        const source = target.sourceFor("local", input, "quick-meeting.m4a")
        return [target.createRun(source, name || "quick meeting", settings)]
      },
      createRunner: () => ({ requestPause: () => {}, run: finish, restart: finish }),
    })
    const setup = await testRender(() => <App />, { width: 100, height: 30 })
    await setup.flush()
    setup.mockInput.pressEnter()
    await setup.flush()
    expect(setup.captureCharFrame()).toContain("quick transcribe · choose media")
    setup.mockInput.pressEnter()
    await setup.flush()
    await setup.mockInput.typeText(mediaPath)
    setup.mockInput.pressEnter()
    await setup.waitForFrame((frame) => frame.includes("Fast transcript output."))
    expect(setup.captureCharFrame()).toContain("quick-meeting — whisper-large-v3-turbo")
    expect(setup.captureCharFrame()).toContain("groq/whisper-large-v3-turbo")
    expect(library.listRuns()).toHaveLength(1)

    setup.renderer.destroy()
    library.close()
  })

  test("quick transcribe reports a missing credential before creating a run", async () => {
    const root = temporary(), mediaPath = join(root, "needs-key.m4a")
    process.env.XDG_CONFIG_HOME = join(root, "config")
    writeFileSync(mediaPath, "audio")
    const library = new Library(join(root, "state"))
    let createCount = 0
    const App = createTranscribeApp(library, {
      requireCredential: () => { throw new Error("GROQ_API_KEY is not set. Export it for this shell and try again; transcribe never stores API keys.") },
      createRuns: async () => { createCount++; return [] },
    })
    const setup = await testRender(() => <App />, { width: 100, height: 30 })
    await setup.flush()
    setup.mockInput.pressEnter()
    await setup.flush()
    setup.mockInput.pressEnter()
    await setup.flush()
    await setup.mockInput.typeText(mediaPath)
    setup.mockInput.pressEnter()
    await setup.flush()

    const frame = setup.captureCharFrame()
    expect(frame).toContain("GROQ_API_KEY is not set")
    expect(frame).toContain("quick transcribe · exact path")
    expect(frame).not.toContain("transcribe message")
    expect(createCount).toBe(0)
    expect(library.listRuns()).toHaveLength(0)

    setup.renderer.destroy()
    library.close()
  })
})
