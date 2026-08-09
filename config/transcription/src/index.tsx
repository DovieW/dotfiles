#!/usr/bin/env bun
import { HELP, VERSION, runCli } from "./cli"
import { Library } from "./storage"
import { runTui } from "./tui"

process.umask(0o077)

const argv = process.argv.slice(2)
if (["version", "--version"].includes(argv[0] || "")) {
  console.log(`transcribe ${VERSION}`)
  process.exit(0)
}
if (["help", "--help", "-h"].includes(argv[0] || "")) {
  console.log(HELP)
  process.exit(0)
}

const library = new Library()
try {
  library.migrateLegacy()
  if (!argv.length) {
    if (!process.stdin.isTTY || !process.stdout.isTTY) { console.error(HELP); process.exitCode = 2 }
    else await runTui(library)
  } else process.exitCode = await runCli(argv, library)
} catch (error) {
  console.error(`transcribe: ${(error as Error).message}`)
  process.exitCode = 1
} finally {
  library.close()
}
