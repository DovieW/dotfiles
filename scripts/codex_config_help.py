"""Descriptions from the public Codex configuration reference and feature registry."""
import json
import re


REFERENCE_URL = "https://learn.chatgpt.com/docs/config-file/config-reference"
HOOKS_URL = "https://learn.chatgpt.com/docs/hooks"
HOOK_DESCRIPTIONS = {
    "SessionStart": "Runs when Codex starts, resumes, clears, compacts, or forks a session.",
    "SessionEnd": "Runs when a Codex session ends.",
    "UserPromptSubmit": "Runs when the user submits a prompt, before Codex processes it.",
    "PreModelRequest": "Runs before Codex sends a request to the model.",
    "PostModelRequest": "Runs after Codex receives a model response.",
    "PreToolUse": "Runs before a tool call. A matching handler can review and sometimes change or block the call.",
    "PermissionRequest": "Runs when a tool call requests permission to proceed.",
    "PostToolUse": "Runs after a tool call, with information about the call and its result.",
    "PreCompact": "Runs before Codex compacts the conversation context.",
    "PostCompact": "Runs after Codex compacts the conversation context.",
    "SubagentStart": "Runs when Codex starts a subagent.",
    "SubagentStop": "Runs when a subagent is about to stop.",
    "Stop": "Runs when the main agent is about to finish its turn.",
    "Interrupt": "Runs when a turn is interrupted.",
}
FEATURE_SOURCE = "codex-rs/features/src/lib.rs"
SOURCE_RAW = "https://raw.githubusercontent.com/openai/codex/rust-v{}/{}"
SOURCE_WEB = "https://github.com/openai/codex/blob/rust-v{}/{}"
SCHEMA_SOURCE = "codex-rs/core/config.schema.json"
QUOTED = r'"(?:[^"\\]|\\.)*"'


def reference_descriptions(text):
    sections = re.split(r"(?m)^##\s+", text)
    config = next((body for body in sections if body.startswith("`config.toml`\n")), "")
    descriptions = {}
    for entry in re.split(r"(?m)^\s*key:\s*(?=\")", config)[1:]:
        key = re.match(QUOTED, entry)
        description = re.search(r"(?m)^\s*description:\s*(" + QUOTED + r")", entry)
        if key and description:
            descriptions[json.loads(key[0])] = json.loads(description[1])
    return descriptions


def feature_descriptions(text):
    enum = re.search(r"(?ms)^pub enum Feature \{\n(.*?)^\}", text)
    if not enum:
        return {}
    comments = re.findall(r"(?m)((?:^[ \t]*///[^\n]*\n)+)^[ \t]*(\w+),[ \t]*$", enum[1])
    by_variant = {
        name: "\n".join(line.strip()[3:].lstrip() for line in doc.splitlines()).strip()
        for doc, name in comments
    }
    return {key: by_variant[variant] for variant, key in re.findall(
        r'\bid:\s*Feature::(\w+),\s*key:\s*"(\w+)"', text) if variant in by_variant and by_variant[variant]}


def reference_fields(entries):
    """Normalize the reference's named placeholders to the schema's path notation."""
    paths = {}
    for key, description in entries.items():
        if not re.fullmatch(r"(?:[\w-]+|<[^>]+>)(?:\[\])?(?:\.(?:[\w-]+|<[^>]+>)(?:\[\])?)*", key):
            continue
        parts = re.findall(r"<[^>]+>|\[\]|[\w-]+", key)
        path = tuple("<name>" if part.startswith("<") else part for part in parts)
        paths[path] = {"text": description, "source": "Codex Configuration Reference",
                       "url": REFERENCE_URL + "#configtoml"}
    return paths
