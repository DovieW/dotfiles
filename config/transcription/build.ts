import solidPlugin from "@opentui/solid/bun-plugin"

const result = await Bun.build({
  entrypoints: ["./src/index.tsx"],
  target: "bun",
  minify: true,
  sourcemap: "linked",
  plugins: [solidPlugin],
  external: [
    "@opentui/core-linux-x64-musl",
    "@opentui/core-linux-arm64",
    "@opentui/core-linux-arm64-musl",
    "@opentui/core-darwin-x64",
    "@opentui/core-darwin-arm64",
    "@opentui/core-win32-x64",
    "@opentui/core-win32-arm64",
  ],
  compile: {
    outfile: "./dist/transcribe",
  },
})

if (!result.success) {
  for (const log of result.logs) console.error(log)
  process.exit(1)
}
