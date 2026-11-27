---
name: chrome-toolkit
description: Choose and use Playwright CLI or Chrome DevTools CLI for browser automation, authenticated workflows, UI testing, debugging, and performance analysis.
---

Use Playwright CLI for navigation, input, snapshots, screenshots, responsive checks, and routine console or network inspection. Use Chrome DevTools CLI for CPU and memory profiling, rendering, extensions, detailed networking, and advanced Chrome DevTools Protocol work. Switch tools or use both when useful. For committed tests, use the project's existing test framework.

Read the relevant upstream guide and its references from the installed CLI package:

- Playwright CLI: `~/.local/share/dotfiles/playwright-cli/current/node_modules/@playwright/cli/skills/playwright-cli/SKILL.md`.
- Chrome DevTools CLI: follow the first symlink from `~/.local/bin/chrome-devtools` with `readlink`. From the target's `bin` directory, read `../lib/node_modules/chrome-devtools-mcp/skills/chrome-devtools-cli/SKILL.md`.

- For routine automation, start an isolated headless session with `playwright-cli -s=NAME open URL --browser=chromium`. Give each task its own name and reuse that session until done. Use headed mode when interactive debugging calls for it.
- Read a fresh snapshot after navigation or structural UI changes. Use screenshots when appearance matters.
- When the task needs a signed-in site or profile extension, use `dot playwright chrome attach --session NAME` from the machine with that Chrome profile. The helper starts a background tab in the existing profile. Selecting a particular personal tab requires the user to select it through the extension.
- If attachment fails, start with `dot playwright chrome status`. Check the live Chrome version, profile window, extension, and wallet before considering another connection method.
- Close your isolated sessions. Use `playwright-cli -s=NAME detach` for attached sessions. Preserve personal tabs and other agents' sessions.
