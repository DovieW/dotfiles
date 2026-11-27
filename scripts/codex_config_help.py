"""Descriptions from the public Codex configuration reference and feature registry."""
import json
import re


REFERENCE_URL = "https://learn.chatgpt.com/docs/config-file/config-reference"
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
