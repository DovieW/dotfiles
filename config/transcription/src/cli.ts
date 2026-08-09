import { existsSync, readFileSync } from "node:fs"
import { basename, join, resolve } from "node:path"
import { loadSettings, saveSettings } from "./config"
import { JobRunner } from "./job"
import { modelsFor } from "./models"
import { commandExists } from "./process"
import { compareTranscripts } from "./providers"
import { createAndRun } from "./service"
import { Library } from "./storage"
import type { Provider, Settings } from "./types"

export const VERSION = "2.0.0"

export const HELP = `Usage:
  transcribe
  transcribe run INPUT [--name NAME] [settings]
  transcribe resume RUN
  transcribe restart RUN
  transcribe compare LEFT RIGHT
  transcribe export RUN --format txt|json --output PATH
  transcribe migrate [PATH...]
  transcribe doctor
  transcribe settings
  transcribe version

Run settings:
  --provider openai|groq|fireworks|youtube-transcript
  --model MODEL                 Provider transcription model
  --language CODE               Remembered language hint
  --diarize / --no-diarize      OpenAI speaker-labelled transcription
  --prompt TEXT                 Context or subtitle cleanup prompt
  --keywords WORD,WORD          gpt-transcribe literal hints
  --chunk-seconds N             Default: 900
  --chunk-overlap-seconds N     Default: 0
  --continuity-chars N          Prior transcript context; forces sequential chunks
  --chunk-concurrency N         Concurrent chunk uploads
  --max-upload-mb N             Default: 24
  --max-retries N               Default: 10
  --initial-retry-seconds N     Default: 30
  --keep-audio / --keep-chunks

Credentials are read only from OPENAI_API_KEY, GROQ_API_KEY, or
FIREWORKS_API_KEY in the current environment and are never stored.`

function take(args: string[], index: number, flag: string): string {
  const value = args[index + 1]
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value.`)
  args.splice(index, 2)
  return value
}

function parseSettings(args: string[]): { settings: Settings, name?: string } {
  const settings = loadSettings()
  let name: string | undefined
  let providerChanged = false, modelChanged = false
  for (let index = 0; index < args.length;) {
    const flag = args[index]!
    if (flag === "--name") { name = take(args, index, flag); continue }
    if (flag === "--provider") { settings.provider = take(args, index, flag) as Provider; settings.diarize = false; providerChanged = true; continue }
    if (flag === "--model") { settings.model = take(args, index, flag); modelChanged = true; continue }
    if (flag === "--language") { settings.language = take(args, index, flag); continue }
    if (flag === "--prompt") { settings.prompt = take(args, index, flag); continue }
    if (flag === "--keywords") { settings.keywords = take(args, index, flag).split(",").map((value) => value.trim()).filter(Boolean); continue }
    const numbers: Record<string, keyof Settings> = { "--chunk-seconds": "chunkSeconds", "--chunk-overlap-seconds": "chunkOverlapSeconds", "--continuity-chars": "continuityChars", "--chunk-concurrency": "chunkConcurrency", "--max-upload-mb": "maxUploadMb", "--max-retries": "maxRetries", "--initial-retry-seconds": "initialRetrySeconds" }
    if (numbers[flag]) { (settings as any)[numbers[flag]!] = Number(take(args, index, flag)); continue }
    if (flag === "--diarize") { settings.diarize = true; settings.provider = "openai"; settings.model = "gpt-4o-transcribe-diarize"; args.splice(index, 1); continue }
    if (flag === "--no-diarize") { settings.diarize = false; if (settings.model === "gpt-4o-transcribe-diarize") settings.model = "gpt-transcribe"; args.splice(index, 1); continue }
    if (flag === "--keep-audio") { settings.keepAudio = true; args.splice(index, 1); continue }
    if (flag === "--keep-chunks") { settings.keepChunks = true; args.splice(index, 1); continue }
    if (flag === "--cleanup") { settings.cleanup = true; settings.provider = "youtube-transcript"; args.splice(index, 1); continue }
    throw new Error(`Unknown option: ${flag}`)
  }
  if (settings.diarize) { settings.provider = "openai"; settings.model = "gpt-4o-transcribe-diarize" }
  else if (providerChanged && !modelChanged) settings.model = modelsFor(settings.provider).find((model) => model.default)?.id || ""
  saveSettings(settings)
  return { settings, name }
}

function transcriptPath(library: Library, reference: string): string {
  const run = library.runByReference(reference)
  if (run) return join(run.artifactDir, "transcript.txt")
  const path = resolve(reference)
  if (!existsSync(path)) throw new Error(`Transcript or run not found: ${reference}`)
  return path
}

export async function runCli(argv: string[], library: Library): Promise<number> {
  const command = argv[0]
  if (command === "help" || command === "--help" || command === "-h") { console.log(HELP); return 0 }
  if (command === "version" || command === "--version") { console.log(`transcribe ${VERSION}`); return 0 }
  if (command === "settings") { console.log(JSON.stringify(loadSettings(), null, 2)); return 0 }
  if (command === "migrate") { const result = library.migrateLegacy(argv.slice(1)); console.log(`Imported ${result.sources} source(s) and ${result.runs} run(s).`); return 0 }
  if (command === "doctor") {
    const checks: Array<[string, boolean, string]> = [
      ["ffmpeg", commandExists("ffmpeg"), "install ffmpeg"], ["ffprobe", commandExists("ffprobe"), "install ffmpeg"], ["yt-dlp", commandExists("yt-dlp"), "install yt-dlp"],
      ["library", existsSync(library.root), library.root], ["OpenAI credential", Boolean(process.env.OPENAI_API_KEY), "optional; export OPENAI_API_KEY when needed"],
      ["Groq credential", Boolean(process.env.GROQ_API_KEY), "optional; export GROQ_API_KEY when needed"], ["Fireworks credential", Boolean(process.env.FIREWORKS_API_KEY), "optional; export FIREWORKS_API_KEY when needed"],
    ]
    for (const [name, ok, detail] of checks) console.log(`${ok ? "[OK]" : name.includes("credential") ? "[--]" : "[FAIL]"} ${name}: ${ok ? "ready" : detail}`)
    return checks.some(([name, ok]) => !ok && !name.includes("credential")) ? 1 : 0
  }
  if (command === "run") {
    const input = argv[1]
    if (!input || input.startsWith("--")) throw new Error("run requires a media path or URL.")
    const rest = argv.slice(2), parsed = parseSettings(rest)
    const results = await createAndRun(library, input, parsed.name, parsed.settings, (event) => console.error(`[${event.type.toUpperCase()}] ${event.message}`))
    for (const run of results) console.log(join(run.artifactDir, "transcript.txt"))
    return 0
  }
  if (command === "resume" || command === "restart") {
    if (!argv[1]) throw new Error(`${command} requires a run reference.`)
    const runner = new JobRunner(library, (event) => console.error(`[${event.type.toUpperCase()}] ${event.message}`))
    const run = command === "restart" ? await runner.restart(argv[1]) : await runner.run(argv[1])
    console.log(`${run.status}: ${run.name}`)
    return run.status === "completed" || run.status === "paused" ? 0 : 1
  }
  if (command === "compare") {
    if (!argv[1] || !argv[2] || argv[3]) throw new Error("compare requires exactly two run references or TXT files.")
    const first = transcriptPath(library, argv[1]), second = transcriptPath(library, argv[2])
    if (first === second) throw new Error("Choose two different transcripts.")
    console.log(await compareTranscripts(basename(first), readFileSync(first, "utf8"), basename(second), readFileSync(second, "utf8")))
    return 0
  }
  if (command === "export") {
    const reference = argv[1]
    if (!reference) throw new Error("export requires a run reference.")
    let format: "txt" | "json" = "txt", output = ""
    for (let index = 2; index < argv.length;) {
      if (argv[index] === "--format") { const value = take(argv, index, "--format"); if (value !== "txt" && value !== "json") throw new Error("--format must be txt or json."); format = value; continue }
      if (argv[index] === "--output") { output = take(argv, index, "--output"); continue }
      throw new Error(`Unknown option: ${argv[index]}`)
    }
    if (!output) throw new Error("export requires --output PATH.")
    console.log(library.exportRun(reference, format, output)); return 0
  }
  throw new Error(`Unknown command: ${command}\n\n${HELP}`)
}
