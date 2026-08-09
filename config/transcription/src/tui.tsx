import { render, useKeyboard, usePaste, useRenderer } from "@opentui/solid"
import type { InputRenderable, ScrollBoxRenderable, SelectOption, SelectRenderable } from "@opentui/core"
import { createEffect, createMemo, createSignal, Show } from "solid-js"
import { existsSync, readFileSync } from "node:fs"
import { basename, join } from "node:path"
import { loadSettings, saveSettings } from "./config"
import { discoverFiles, MEDIA_EXTENSIONS, TEXT_EXTENSIONS, type FileChoice } from "./files"
import { fuzzyOptions } from "./fuzzy"
import { expandUserPath, pathSuggestions } from "./paths"
import { JobRunner, type JobEvent } from "./job"
import { modelsFor } from "./models"
import { compareTranscripts, requireCredential } from "./providers"
import { createRuns, suggestedRunName } from "./service"
import { Library } from "./storage"
import type { Provider, RunRecord, Settings, SourceRecord, TranscriptDocument } from "./types"
import { findTextMatches, formatTranscript, viewerMetadata } from "./viewer"

type Screen = "home" | "quick-input" | "quick-location" | "new-input" | "new-location" | "new-name" | "new-provider" | "new-model" | "review" | "active" | "sources" | "runs" | "run" | "compare-mode" | "compare-source" | "compare-runs" | "compare-external-a" | "compare-external-a-input" | "compare-external-b" | "compare-external-b-input" | "compare-result" | "settings" | "setting-input" | "help" | "message"

const blue = "#58a6ff", green = "#7ee787", muted = "#8b949e", red = "#ff7b72", panel = "#161b22"

function options(entries: Array<[string, string, unknown?]>): SelectOption[] {
  return entries.map(([name, description, value]) => ({ name, description, value: value ?? name }))
}

type TuiRunner = Pick<JobRunner, "requestPause" | "run" | "restart">
export interface TuiDependencies {
  createRuns?: typeof createRuns
  createRunner?: (library: Library, notify: (event: JobEvent) => void) => TuiRunner
  requireCredential?: (provider: Provider) => unknown
}

export function createTranscribeApp(library: Library, dependencies: TuiDependencies = {}) {
  let settings = loadSettings()
  let input = "", runName = ""
  let compareA = "", compareB = "", editingKey: keyof Settings | null = null
  let activeRunner: TuiRunner | null = null
  let settingsReturn: Screen = "home", pickerReturn: Screen = "settings"
  let viewerReturn: Screen = "home", messageReturn: Screen = "home"
  let mediaCache: FileChoice[] | null = null, textCache: FileChoice[] | null = null
  const createRunsFor = dependencies.createRuns || createRuns
  const createRunner = dependencies.createRunner || ((target, notify) => new JobRunner(target, notify))
  const requireCredentialFor = dependencies.requireCredential || requireCredential

  function App() {
    const renderer = useRenderer()
    const [screen, setScreen] = createSignal<Screen>("home")
    const [message, setMessage] = createSignal("")
    const [error, setError] = createSignal("")
    const [jobEvent, setJobEvent] = createSignal<JobEvent | null>(null)
    const [sourcesVersion, setSourcesVersion] = createSignal(0)
    const [settingsVersion, setSettingsVersion] = createSignal(0)
    const [compareSelected, setCompareSelected] = createSignal<string[]>([])
    const [menuQuery, setMenuQuery] = createSignal("")
    const [pathQuery, setPathQuery] = createSignal("")
    const [viewerQuery, setViewerQuery] = createSignal("")
    const [viewerText, setViewerText] = createSignal("")
    const [viewerRawText, setViewerRawText] = createSignal("")
    const [viewerTitle, setViewerTitle] = createSignal("viewer")
    const [viewerDocument, setViewerDocument] = createSignal<TranscriptDocument | null>(null)
    const [viewerRunId, setViewerRunId] = createSignal<string | null>(null)
    const [viewerNotice, setViewerNotice] = createSignal("")
    const [selectedSource, setSelectedSource] = createSignal<SourceRecord | null>(null)
    const [selectedRun, setSelectedRun] = createSignal<RunRecord | null>(null)
    const sources = createMemo(() => { sourcesVersion(); return library.listSources() })
    const runs = createMemo(() => { sourcesVersion(); const source = selectedSource(); return source ? library.listRunsForSource(source.id) : [] })

    const go = (next: Screen) => { setError(""); setMenuQuery(""); setPathQuery(""); if (next !== "compare-result") setViewerQuery(""); setScreen(next) }
    const fail = (reason: unknown) => setError((reason as Error).message || String(reason))
    const showFailure = (reason: unknown, returnTo: Screen) => {
      messageReturn = returnTo
      setMessage("")
      go("message")
      fail(reason)
    }
    const home = () => { setSelectedSource(null); setSelectedRun(null); setCompareSelected([]); go("home") }
    const back = () => {
      const parent: Partial<Record<Screen, Screen>> = {
        "quick-input": "home", "quick-location": "quick-input", "new-input": "home", "new-location": "new-input", "new-name": "new-input", "new-provider": pickerReturn, "new-model": pickerReturn,
        review: "new-name", sources: "home", runs: "sources", run: selectedSource() ? "runs" : "home",
        "compare-mode": "home", "compare-source": "compare-mode", "compare-runs": "compare-source",
        "compare-external-a": "compare-mode", "compare-external-a-input": "compare-external-a",
        "compare-external-b": "compare-external-a", "compare-external-b-input": "compare-external-b",
        "compare-result": viewerReturn, settings: settingsReturn, "setting-input": editingKey ? "settings" : "run",
        help: "home", message: messageReturn,
      }
      const current = screen(), target = parent[current] || "home"
      if (current === "compare-runs") setCompareSelected([])
      if (current === "setting-input" && editingKey) editingKey = null
      if (target === "home") home()
      else go(target)
    }
    useKeyboard((key) => {
      if (key.name === "escape") {
        if (screen() === "active") return
        if (menuQuery() || pathQuery() || viewerQuery()) { setMenuQuery(""); setPathQuery(""); setViewerQuery(""); key.preventDefault(); key.stopPropagation(); return }
        if (screen() === "home") renderer.destroy()
        else back()
      }
      if (key.name === "c" && key.ctrl) {
        if (screen() === "active" && activeRunner) {
          activeRunner.requestPause()
          setJobEvent({ type: "status", message: "Pausing after active requests finish…" })
        } else renderer.destroy()
      }
    })

    const acceptInput = (value: string) => {
      input = value.trim()
      if (!input) return fail("Input cannot be blank.")
      runName = suggestedRunName(input, settings)
      go("new-name")
    }

    const prepareViewer = (title: string, text: string, run: RunRecord | null, document: TranscriptDocument | null, returnTo: Screen) => {
      viewerReturn = returnTo
      setViewerTitle(title)
      setViewerRawText(document?.text || text)
      setViewerText(document ? formatTranscript(document) : text)
      setViewerDocument(document)
      setViewerRunId(run?.id || null)
      setViewerNotice("")
      setViewerQuery("")
      go("compare-result")
    }

    const openRunViewer = (run: RunRecord, returnTo: Screen) => {
      const textPath = join(run.artifactDir, "transcript.txt")
      if (!existsSync(textPath)) throw new Error("Transcript is not available yet.")
      let document: TranscriptDocument | null = null
      const jsonPath = join(run.artifactDir, "transcript.json")
      if (existsSync(jsonPath)) {
        try { document = JSON.parse(readFileSync(jsonPath, "utf8")) as TranscriptDocument } catch {}
      }
      prepareViewer(run.name, readFileSync(textPath, "utf8"), run, document, returnTo)
    }

    const startRuns = async (showViewer = false, uniqueName = false, failureReturn: Screen = "review") => {
      try {
        go("active")
        const created = await createRunsFor(library, input, runName || undefined, settings, uniqueName)
        const runner = createRunner(library, setJobEvent)
        activeRunner = runner
        for (const run of created) {
          setSelectedRun(run)
          await runner.run(run.id)
        }
        setSourcesVersion((value) => value + 1)
        const completed = library.requireRun(selectedRun()!.id)
        setSelectedRun(completed)
        activeRunner = null
        if (showViewer && completed.status === "completed") openRunViewer(completed, "home")
        else go("run")
      } catch (reason) { activeRunner = null; showFailure(reason, failureReturn) }
    }

    const startQuick = (value: string) => {
      const location = expandUserPath(value.trim())
      if (!location) return fail("Choose a media file.")
      if (/^https?:\/\//i.test(location)) return fail("Quick Transcribe accepts a local media file. Use New transcription for URLs.")
      if (!existsSync(location)) return fail(`Media file not found: ${location}`)
      if (settings.provider === "youtube-transcript") return fail("Quick Transcribe requires an audio provider. Change the remembered provider in Settings.")
      try { requireCredentialFor(settings.provider) } catch (reason) { return fail(reason) }
      input = location
      runName = suggestedRunName(location, settings)
      void startRuns(true, true, "quick-input")
    }

    const compare = async (first: string, second: string) => {
      try {
        const returnTo = screen()
        prepareViewer("comparison", "Comparing with OpenAI gpt-5.6-luna…", null, null, returnTo)
        const firstText = readFileSync(first, "utf8"), secondText = readFileSync(second, "utf8")
        const result = await compareTranscripts(basename(first), firstText, basename(second), secondText)
        setViewerRawText(result); setViewerText(result)
      } catch (reason) { showFailure(reason, viewerReturn) }
    }

    const settingRows = (): SelectOption[] => options([
      ["Provider", settings.provider, "provider"], ["Model", settings.diarize ? "gpt-4o-transcribe-diarize" : settings.model, "model"],
      ["Language", settings.language, "language"], ["Diarization", settings.diarize ? "on" : "off", "diarize"],
      ["YouTube subtitle cleanup", settings.cleanup ? "on" : "off", "cleanup"], ["Prompt", settings.prompt || "none", "prompt"], ["Keywords", settings.keywords.join(", ") || "none", "keywords"],
      ["Chunk seconds", String(settings.chunkSeconds), "chunkSeconds"], ["Chunk overlap", String(settings.chunkOverlapSeconds), "chunkOverlapSeconds"],
      ["Continuity characters", String(settings.continuityChars), "continuityChars"], ["Chunk concurrency", String(settings.chunkConcurrency), "chunkConcurrency"],
      ["Maximum upload MB", String(settings.maxUploadMb), "maxUploadMb"], ["Maximum retries", String(settings.maxRetries), "maxRetries"],
      ["Initial retry seconds", String(settings.initialRetrySeconds), "initialRetrySeconds"], ["Keep audio", settings.keepAudio ? "yes" : "no", "keepAudio"],
      ["Keep chunks", settings.keepChunks ? "yes" : "no", "keepChunks"], ["Save and return", "Persist these defaults", "done"],
    ])

    const editSetting = (key: keyof Settings | "done") => {
      if (key === "done") { try { saveSettings(settings); go(settingsReturn) } catch (reason) { fail(reason) }; return }
      if (key === "provider") { pickerReturn = "settings"; go("new-provider"); return }
      if (key === "model") { pickerReturn = "settings"; go("new-model"); return }
      if (["diarize", "cleanup", "keepAudio", "keepChunks"].includes(key)) {
        ;(settings as any)[key] = !(settings as any)[key]
        if (key === "diarize" && settings.diarize) { settings.provider = "openai"; settings.model = "gpt-4o-transcribe-diarize" }
        if (key === "diarize" && !settings.diarize) settings.model = "gpt-transcribe"
        setSettingsVersion((value) => value + 1); return
      }
      editingKey = key
      go("setting-input")
    }

    const submitSetting = (value: string) => {
      if (!editingKey) return
      if (editingKey === "keywords") settings.keywords = value.split(",").map((item) => item.trim()).filter(Boolean)
      else if (["chunkSeconds", "chunkOverlapSeconds", "continuityChars", "chunkConcurrency", "maxUploadMb", "maxRetries", "initialRetrySeconds"].includes(editingKey)) (settings as any)[editingKey] = Number(value)
      else (settings as any)[editingKey] = value
      editingKey = null; go("settings")
    }

    const Header = (props: { title: string, subtitle?: string }) => <box height={4} flexDirection="column"><text fg={blue}><strong>transcribe</strong>  {props.title}</text><text fg={muted}>{props.subtitle || "↑/↓ navigate  Enter select  Esc back  Ctrl-C quit"}</text></box>
    const ErrorLine = () => <Show when={error()}><text fg={red}>Error: {error()}</text></Show>
    const Menu = (props: { title: string, subtitle?: string, items: SelectOption[], select: (option: SelectOption) => void }) => {
      const filtered = createMemo(() => fuzzyOptions(menuQuery(), props.items))
      const visible = createMemo(() => filtered().length ? filtered() : options([["No matches", "Backspace to broaden the search", "__no_match__"]]))
      useKeyboard((key) => {
        if (key.ctrl && key.name === "u") { setMenuQuery(""); key.preventDefault(); return }
        if (key.name === "backspace") { setMenuQuery((value) => [...value].slice(0, -1).join("")); key.preventDefault(); return }
        if (!key.ctrl && !key.meta && !key.option && key.sequence.length === 1 && key.sequence >= " ") {
          setMenuQuery((value) => value + key.sequence)
          key.preventDefault()
        }
      })
      usePaste((event) => {
        const pasted = new TextDecoder().decode(event.bytes).replace(/\s+/g, " ")
        setMenuQuery((value) => value + pasted)
        event.preventDefault()
      })
      return <box flexDirection="column" width="100%" height="100%" padding={1}><Header title={props.title} subtitle={props.subtitle || "Type to fuzzy-find  ↑/↓ navigate  Enter select  Esc clear/back"}/><ErrorLine/><box flexDirection="row" height={2} paddingLeft={1}><text fg={blue}>Search › </text><text>{menuQuery() || "type to filter…"}</text></box><box border borderColor="#30363d" backgroundColor={panel} padding={1} flexGrow={1}><select focused width="100%" height="100%" options={visible()} wrapSelection showDescription onSelect={(_, option) => option && option.value !== "__no_match__" && props.select(option)} /></box></box>
    }

    const PathEntry = (props: { title: string, placeholder: string, extensions: string[], submit: (value: string) => void, allowUrls?: boolean }) => {
      let picker: SelectRenderable | undefined, field: InputRenderable | undefined
      const suggestions = createMemo(() => pathSuggestions(pathQuery(), props.extensions))
      const suggestionOptions = createMemo(() => suggestions().length
        ? suggestions().map((item) => ({ name: item.name, description: item.description, value: item.path }))
        : options([["No path suggestions", props.allowUrls ? "Keep typing, paste a path or URL, or press Esc" : "Keep typing, paste a local path, or press Esc", "__none__"]]))
      const complete = () => {
        const selected = picker?.getSelectedOption()
        if (!selected || selected.value === "__none__") return
        setPathQuery(String(selected.value))
        field?.focus()
      }
      useKeyboard((key) => {
        if (key.ctrl && key.name === "u") { setPathQuery(""); key.preventDefault(); return }
        if (key.name === "tab") { complete(); key.preventDefault(); return }
        if (["down", "arrowdown"].includes(key.name)) { picker?.moveDown(); key.preventDefault(); return }
        if (["up", "arrowup"].includes(key.name)) { picker?.moveUp(); key.preventDefault() }
      })
      return <box flexDirection="column" width="100%" height="100%" padding={1}><Header title={props.title} subtitle={`Type or paste a ${props.allowUrls ? "path/URL" : "local path"}  Tab completes  ↑/↓ suggestions  Enter accepts`}/><ErrorLine/><box border borderColor={blue} height={3} paddingLeft={1} paddingRight={1}><input ref={(value) => field = value} focused width="100%" value={pathQuery()} placeholder={props.placeholder} onInput={setPathQuery} onSubmit={(value) => props.submit(String(value))}/></box><box border borderColor="#30363d" backgroundColor={panel} padding={1} flexGrow={1}><select ref={(value) => picker = value} width="100%" height="100%" options={suggestionOptions()} wrapSelection showDescription onSelect={(_, option) => { if (option?.value && option.value !== "__none__") { setPathQuery(String(option.value)); field?.focus() } }}/></box></box>
    }

    const openViewerEditor = async () => {
      const runId = viewerRunId()
      if (!runId) { setViewerNotice("This result is not attached to an editable run."); return }
      const path = join(library.requireRun(runId).artifactDir, "transcript.txt")
      const editor = process.env.VISUAL || process.env.EDITOR || Bun.which("nvim") || Bun.which("vim") || Bun.which("vi")
      if (!editor) { setViewerNotice("Set $EDITOR or $VISUAL to open transcripts."); return }
      const command = typeof editor === "string" ? editor.trim().split(/\s+/).filter(Boolean) : [String(editor)]
      renderer.suspend()
      try {
        const exitCode = await Bun.spawn([...command, path], { stdin: "inherit", stdout: "inherit", stderr: "inherit" }).exited
        setViewerNotice(exitCode === 0 ? "Editor closed." : `Editor exited with status ${exitCode}.`)
      } catch (reason) { setViewerNotice(`Could not open editor: ${(reason as Error).message}`) }
      finally { renderer.resume() }
    }

    const Viewer = () => {
      let scroller: ScrollBoxRenderable | undefined
      const [matchIndex, setMatchIndex] = createSignal(0)
      const matches = createMemo(() => findTextMatches(viewerText(), viewerQuery()))
      const jump = (next: number) => {
        const available = matches()
        if (!available.length) return
        const index = (next + available.length) % available.length
        setMatchIndex(index)
        scroller?.scrollTo({ x: 0, y: Math.max(0, available[index]!.line - 2) })
      }
      createEffect(() => {
        viewerQuery()
        const available = matches()
        setMatchIndex(0)
        if (available[0]) scroller?.scrollTo({ x: 0, y: Math.max(0, available[0].line - 2) })
      })
      useKeyboard((key) => {
        if (key.ctrl && key.name === "e") { void openViewerEditor(); key.preventDefault(); return }
        if (key.ctrl && key.name === "y") {
          const copied = renderer.copyToClipboardOSC52(viewerRawText())
          setViewerNotice(copied ? "Transcript copied to the terminal clipboard." : "This terminal did not accept clipboard copy.")
          key.preventDefault(); return
        }
        if (key.ctrl && key.name === "u") { setViewerQuery(""); key.preventDefault(); return }
        if (key.name === "backspace" && viewerQuery()) { setViewerQuery((value) => [...value].slice(0, -1).join("")); key.preventDefault(); return }
        if ((key.name === "return" || key.name === "enter") && viewerQuery()) { jump(matchIndex() + (key.shift ? -1 : 1)); key.preventDefault(); return }
        if (!key.ctrl && !key.meta && !key.option && key.sequence.length === 1 && key.sequence >= " ") {
          setViewerQuery((value) => value + key.sequence)
          key.preventDefault()
        }
      })
      usePaste((event) => {
        setViewerQuery((value) => value + new TextDecoder().decode(event.bytes).replace(/\s+/g, " "))
        event.preventDefault()
      })
      const metadata = () => viewerMetadata(viewerRunId() ? library.requireRun(viewerRunId()!) : null, viewerDocument())
      const searchStatus = () => viewerQuery()
        ? matches().length ? `${matchIndex() + 1}/${matches().length} · line ${matches()[matchIndex()]!.line + 1}` : "no matches"
        : ""
      return <box flexDirection="column" width="100%" height="100%" padding={1}><Header title={viewerTitle()} subtitle="Type=find  Enter=next  Shift-Enter=prev  ^Y=copy  ^E=editor  Esc=back"/><box height={1}><text fg={muted}>{metadata()}</text></box><box height={2}><text fg={blue}>Find › {viewerQuery() || "type to search…"}  {searchStatus()}</text></box><Show when={viewerNotice()}><box height={1}><text fg={green}>{viewerNotice()}</text></box></Show><scrollbox ref={(value) => scroller = value} focused border borderColor="#30363d" padding={1} flexGrow={1}><text selectable>{viewerText()}</text></scrollbox></box>
    }

    const mediaChoices = () => mediaCache ??= discoverFiles(MEDIA_EXTENSIONS)
    const textChoices = () => textCache ??= discoverFiles(TEXT_EXTENSIONS)
    const fileItems = (choices: FileChoice[], manualDescription: string, manualName = "Enter an exact path or URL…"): SelectOption[] => [
      { name: manualName, description: manualDescription, value: "__manual__" },
      ...choices.map((choice) => ({ name: choice.name, description: choice.description, value: choice.path })),
    ]

    return <>
      <Show when={screen() === "home"}><Menu title="home" items={options([
        ["Quick Transcribe", `Choose a local file and start with ${settings.provider}/${settings.diarize ? "gpt-4o-transcribe-diarize" : settings.model}`, "quick"],
        ["New transcription", "Name the run and review settings before starting", "new"], ["Library", "Browse sources and named runs", "library"],
        ["Compare transcripts", "Choose two library runs or text files", "compare"], ["Settings", "Remember provider, model, and job defaults", "settings"],
        ["Help", "Commands, keys, storage, and credentials", "help"], ["Quit", "Return to the shell", "quit"],
      ])} select={(option) => { if (option.value === "quick") go("quick-input"); else if (option.value === "new") go("new-input"); else if (option.value === "library") go("sources"); else if (option.value === "compare") go("compare-mode"); else if (option.value === "settings") { settingsReturn = "home"; go("settings") } else if (option.value === "help") go("help"); else renderer.destroy() }}/></Show>

      <Show when={screen() === "quick-input"}><Menu title="quick transcribe · choose media" subtitle={`Starts immediately with ${settings.provider}/${settings.diarize ? "gpt-4o-transcribe-diarize" : settings.model} · ${settings.language}`} items={fileItems(mediaChoices(), "Enter a local media path not listed below", "Enter an exact local path…")} select={(option) => option.value === "__manual__" ? go("quick-location") : startQuick(String(option.value))}/></Show>
      <Show when={screen() === "quick-location"}><PathEntry title="quick transcribe · exact path" placeholder="local media path" extensions={MEDIA_EXTENSIONS} submit={startQuick}/></Show>
      <Show when={screen() === "new-input"}><Menu title="new transcription · media" items={fileItems(mediaChoices(), "Use this for a YouTube URL or a file not listed below")} select={(option) => option.value === "__manual__" ? go("new-location") : acceptInput(String(option.value))}/></Show>
      <Show when={screen() === "new-location"}><PathEntry title="new transcription · exact location" placeholder="path or URL" extensions={MEDIA_EXTENSIONS} submit={acceptInput} allowUrls/></Show>
      <Show when={screen() === "new-name"}><box flexDirection="column" padding={1}><Header title="name this run" subtitle={`Suggested: ${runName}`}/><input focused value={runName} onSubmit={(value) => { runName = String(value).trim(); if (!runName) return fail("Run name cannot be blank."); go("review") }}/><ErrorLine/></box></Show>
      <Show when={screen() === "new-provider"}><Menu title="provider" items={options([
        ["OpenAI", "gpt-transcribe and specialized models", "openai"], ["Groq", "Whisper Large v3", "groq"], ["Fireworks", "Whisper v3", "fireworks"], ["YouTube transcript", "Use existing English subtitles", "youtube-transcript"],
      ])} select={(option) => { settings.provider = option.value as Provider; settings.diarize = false; settings.model = modelsFor(settings.provider).find((model) => model.default)?.id || "youtube"; setSettingsVersion((value) => value + 1); go(pickerReturn) }}/></Show>
      <Show when={screen() === "new-model"}><Menu title="model" items={settings.provider === "youtube-transcript" ? options([["YouTube subtitles", "Use the best available English subtitles", "youtube"]]) : modelsFor(settings.provider).map((model) => ({ name: model.label, description: `${model.id}${model.diarization ? " · speaker labels" : ""}`, value: model.id }))} select={(option) => { settings.model = String(option.value); settings.diarize = settings.model === "gpt-4o-transcribe-diarize"; setSettingsVersion((value) => value + 1); go(pickerReturn) }}/></Show>
      <Show when={screen() === "review"}><Menu title="review" subtitle="Your settings are remembered. Change anything or start." items={options([
        ["Start transcription", `${settings.provider} · ${settings.diarize ? "gpt-4o-transcribe-diarize" : settings.model} · ${settings.language}`, "start"],
        ["Change provider", settings.provider, "provider"], ["Change model", settings.model, "model"], ["All settings", "Chunking, retries, prompts, language, and artifacts", "settings"], ["Cancel", "Return home", "cancel"],
      ])} select={(option) => { if (option.value === "start") void startRuns(); else if (option.value === "provider") { pickerReturn = "review"; go("new-provider") } else if (option.value === "model") { pickerReturn = "review"; go("new-model") } else if (option.value === "settings") { settingsReturn = "review"; go("settings") } else home() }}/></Show>

      <Show when={screen() === "active"}><box flexDirection="column" padding={1}><Header title="active run" subtitle="Ctrl-C requests a safe pause after active chunk requests finish"/><box border borderColor={blue} padding={1} flexDirection="column"><text fg={green}>{jobEvent()?.message || "Starting…"}</text><Show when={jobEvent()?.total}><text>{jobEvent()?.completed || 0}/{jobEvent()?.total} chunks completed</text></Show><Show when={selectedRun()}><text fg={muted}>{selectedRun()?.name}</text></Show></box></box></Show>

      <Show when={screen() === "sources"}><Menu title="library · sources" items={sources().length ? sources().map((source) => ({ name: source.title, description: `${source.kind} · ${library.listRunsForSource(source.id).length} run(s)`, value: source.id })) : options([["No sources yet", "Create a transcription first", "none"]])} select={(option) => { if (option.value === "none") return; setSelectedSource(library.requireSource(String(option.value))); go("runs") }}/></Show>
      <Show when={screen() === "runs"}><Menu title={`library · ${selectedSource()?.title || "runs"}`} items={runs().length ? runs().map((run) => ({ name: run.name, description: `${run.status} · ${run.provider}/${run.model}`, value: run.id })) : options([["No runs", "This source has no runs", "none"]])} select={(option) => { if (option.value === "none") return; setSelectedRun(library.requireRun(String(option.value))); go("run") }}/></Show>
      <Show when={screen() === "run" && selectedRun()}><Menu title={selectedRun()?.name || "run"} subtitle={`${selectedRun()?.status} · ${selectedRun()?.provider}/${selectedRun()?.model}`} items={options([
        ["View transcript", "Read-only TXT viewer", "view"], ["Resume", "Continue incomplete chunks", "resume"], ["Restart", "Restart transcription and retain shared audio", "restart"],
        ["Duplicate settings", "Create a separately named run", "duplicate"], ["Export TXT", "Copy transcript to a chosen path", "export-txt"], ["Export JSON", "Copy structured transcript", "export-json"],
        ["Rename", "Change display name", "rename"], ["Delete permanently", "Requires exact run-name confirmation", "delete"], ["Back", "Return to runs", "back"],
      ])} select={(option) => {
        const run = selectedRun()!
        if (option.value === "view") { try { openRunViewer(run, "run") } catch (reason) { fail(reason) } }
        else if (option.value === "resume" || option.value === "restart") { go("active"); const runner = createRunner(library, setJobEvent); activeRunner = runner; void (option.value === "restart" ? runner.restart(run.id) : runner.run(run.id)).then((value) => { activeRunner = null; setSelectedRun(value); setSourcesVersion((v) => v + 1); go("run") }).catch((reason) => { activeRunner = null; showFailure(reason, "run") }) }
        else if (["duplicate", "rename", "delete", "export-txt", "export-json"].includes(String(option.value))) { editingKey = null; setMessage(String(option.value)); go("setting-input") }
        else go("runs")
      }}/></Show>

      <Show when={screen() === "settings"}><Menu title="settings" subtitle="Every value below is visible, editable, and persisted only when saved." items={(settingsVersion(), settingRows())} select={(option) => editSetting(option.value as keyof Settings | "done")}/></Show>
      <Show when={screen() === "setting-input"}><box flexDirection="column" padding={1}><Header title={editingKey ? `edit ${String(editingKey)}` : message()} subtitle={message() === "delete" ? `Type exactly: ${selectedRun()?.name}` : "Enter a value and press Enter"}/><input focused value={editingKey ? String((settings as any)[editingKey] ?? "") : ""} onSubmit={(submitted) => {
        try {
          const value = String(submitted)
          if (editingKey) return submitSetting(value)
          const action = message(), run = selectedRun()!
          if (action === "duplicate") setSelectedRun(library.duplicateRun(run.id, value))
          else if (action === "rename") setSelectedRun(library.updateRun(run.id, { name: value }))
          else if (action === "delete") { if (value !== run.name) throw new Error("Confirmation did not match the run name."); library.deleteRun(run.id); setSelectedRun(null); setSourcesVersion((v) => v + 1); return go("sources") }
          else if (action === "export-txt") library.exportRun(run.id, "txt", value)
          else if (action === "export-json") library.exportRun(run.id, "json", value)
          setSourcesVersion((v) => v + 1); go("run")
        } catch (reason) { fail(reason) }
      }}/><ErrorLine/></box></Show>

      <Show when={screen() === "compare-mode"}><Menu title="compare transcripts" items={options([["Library runs", "Choose a source, then exactly two completed runs", "library"], ["External TXT files", "Enter two text-file paths", "external"]])} select={(option) => go(option.value === "library" ? "compare-source" : "compare-external-a")}/></Show>
      <Show when={screen() === "compare-source"}><Menu title="compare · source" items={sources().filter((source) => source.kind !== "playlist" && library.listRunsForSource(source.id).filter((run) => run.status === "completed").length >= 2).map((source) => ({ name: source.title, description: `${library.listRunsForSource(source.id).filter((run) => run.status === "completed").length} completed runs`, value: source.id }))} select={(option) => { setSelectedSource(library.requireSource(String(option.value))); go("compare-runs") }}/></Show>
      <Show when={screen() === "compare-runs"}><Menu title={`compare · ${selectedSource()?.title || "runs"}`} subtitle={`Select two runs (${compareSelected().length}/2 selected)`} items={(selectedSource() ? library.listRunsForSource(selectedSource()!.id) : []).filter((run) => run.status === "completed").map((run) => ({ name: `${compareSelected().includes(run.id) ? "✓ " : ""}${run.name}`, description: `${run.provider}/${run.model}`, value: run.id }))} select={(option) => {
        const runId = String(option.value), current = compareSelected(), next = current.includes(runId) ? current.filter((id) => id !== runId) : [...current, runId]
        setCompareSelected(next)
        if (next.length === 2) { const [a, b] = next.map((id) => library.requireRun(id)); void compare(join(a!.artifactDir, "transcript.txt"), join(b!.artifactDir, "transcript.txt")) }
      }}/></Show>
      <Show when={screen() === "compare-external-a"}><Menu title="compare · transcript A" items={fileItems(textChoices(), "Enter a text file not listed below")} select={(option) => { if (option.value === "__manual__") go("compare-external-a-input"); else { compareA = String(option.value); go("compare-external-b") } }}/></Show>
      <Show when={screen() === "compare-external-a-input"}><PathEntry title="compare · transcript A · exact path" placeholder="first.txt" extensions={TEXT_EXTENSIONS} submit={(value) => { compareA = value; go("compare-external-b") }}/></Show>
      <Show when={screen() === "compare-external-b"}><Menu title="compare · transcript B" items={fileItems(textChoices().filter((choice) => choice.path !== compareA), "Enter a text file not listed below")} select={(option) => { if (option.value === "__manual__") go("compare-external-b-input"); else { compareB = String(option.value); void compare(compareA, compareB) } }}/></Show>
      <Show when={screen() === "compare-external-b-input"}><PathEntry title="compare · transcript B · exact path" placeholder="second.txt" extensions={TEXT_EXTENSIONS} submit={(value) => { compareB = value; void compare(compareA, compareB) }}/></Show>
      <Show when={screen() === "compare-result"}><Viewer/></Show>
      <Show when={screen() === "help"}><box flexDirection="column" padding={1}><Header title="help"/><scrollbox focused border padding={1} flexGrow={1}><text selectable>{`transcribe is a central, resumable transcription library.\n\nQuick Transcribe\n  Choose a local media file and start immediately with remembered settings.\n  The completed transcript opens directly in the viewer and remains in the library.\n\nMenus\n  Type  fuzzy-find the active menu\n  ↑/↓  move\n  Enter choose\n  Esc   clear search, then go back (quit from home)\n  Ctrl-U clear search\n  Ctrl-C quit; during jobs it requests a safe pause\n\nViewer\n  Type        search transcript\n  Enter       next match\n  Shift-Enter previous match\n  Ctrl-Y      copy entire transcript\n  Ctrl-E      open transcript in $EDITOR\n\nCredentials\n  Export OPENAI_API_KEY, GROQ_API_KEY, or FIREWORKS_API_KEY only when needed. Keys are never saved.\n\nStorage\n  Config: ~/.config/dotfiles/transcribe/config.json\n  Library: ~/.local/state/dotfiles/transcribe\n\nCLI\n  transcribe run INPUT --name NAME\n  transcribe resume RUN\n  transcribe restart RUN\n  transcribe compare LEFT RIGHT\n  transcribe export RUN --format txt|json --output PATH\n  transcribe doctor`}</text></scrollbox></box></Show>
      <Show when={screen() === "message"}><box flexDirection="column" padding={1}><Header title="message"/><ErrorLine/><text>{message()}</text><text fg={muted}>Press Esc to go back.</text></box></Show>
    </>
  }
  return App
}

export async function runTui(library: Library): Promise<void> {
  const App = createTranscribeApp(library)
  await new Promise<void>((resolve, reject) => {
    void render(() => <App />, { exitOnCtrlC: false, onDestroy: resolve }).catch(reject)
  })
}
