export async function command(args: string[], options: { cwd?: string, stdin?: "ignore" | "inherit", quiet?: boolean } = {}): Promise<string> {
  const child = Bun.spawn(args, {
    cwd: options.cwd,
    stdin: options.stdin ?? "ignore",
    stdout: "pipe",
    stderr: "pipe",
  })
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ])
  if (exitCode !== 0) throw new Error(`${args[0]} failed (${exitCode}): ${stderr.trim() || stdout.trim()}`)
  if (!options.quiet && stderr.trim()) globalThis.process.stderr.write(stderr)
  return stdout
}

export function commandExists(name: string): boolean {
  const path = Bun.which(name)
  return typeof path === "string" && path.length > 0
}
