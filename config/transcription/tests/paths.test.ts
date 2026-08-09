import { afterEach, describe, expect, test } from "bun:test"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { pathSuggestions } from "../src/paths"

const roots: string[] = []
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }) })

describe("path completion", () => {
  test("fuzzy-completes directories and supported files", () => {
    const root = join("/tmp", `transcribe-path-test-${crypto.randomUUID()}`)
    roots.push(root)
    mkdirSync(join(root, "Recordings"), { recursive: true })
    writeFileSync(join(root, "meeting-audio.m4a"), "audio")
    writeFileSync(join(root, "meeting-notes.txt"), "notes")

    expect(pathSuggestions(`${root}/rec`, [".m4a"])[0]?.path).toBe(`${root}/Recordings/`)
    expect(pathSuggestions(`${root}/maud`, [".m4a"])[0]?.path).toBe(`${root}/meeting-audio.m4a`)
    expect(pathSuggestions(`${root}/meet`, [".m4a"]).map((item) => item.path)).not.toContain(`${root}/meeting-notes.txt`)
  })

  test("does not treat URLs as filesystem paths", () => {
    expect(pathSuggestions("https://youtu.be/example", [".m4a"])).toEqual([])
  })
})
