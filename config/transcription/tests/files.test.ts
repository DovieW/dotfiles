import { afterEach, describe, expect, test } from "bun:test"
import { mkdirSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { discoverFiles } from "../src/files"

const roots: string[] = []
afterEach(() => { for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true }) })

describe("file discovery", () => {
  test("finds supported files and skips generated dependency trees", () => {
    const root = join("/tmp", `transcribe-files-test-${crypto.randomUUID()}`)
    roots.push(root)
    mkdirSync(join(root, "meetings"), { recursive: true })
    mkdirSync(join(root, "node_modules", "package"), { recursive: true })
    writeFileSync(join(root, "meetings", "standup.m4a"), "audio")
    writeFileSync(join(root, "meetings", "notes.txt"), "text")
    writeFileSync(join(root, "node_modules", "package", "hidden.m4a"), "audio")

    const files = discoverFiles([".m4a"], [root])
    expect(files.map((file) => file.name)).toEqual(["standup.m4a"])
    expect(files[0]?.description).toContain("meetings")
  })
})
