"""Generate the local OSD item from Plasma's installed renderer."""

from pathlib import Path
import sys


def replace(source, original, replacement, count=1):
    if source.count(original) != count:
        raise SystemExit(f"Unsupported Plasma OsdItem.qml layout near {original.strip()!r}")
    return source.replace(original, replacement)


def render(source):
    showing_progress = "    property bool showingProgress: false\n"
    source = replace(
        source,
        showing_progress,
        showing_progress
        + "    readonly property real progressTarget: showingProgress\n"
        + "        ? Math.max(0, Math.min(osdMaxValue, Number(osdValue))) : 0\n"
        + "    property real barProgress: progressTarget\n",
    )
    source = replace(source, "value: Number(root.osdValue)", "value: root.barProgress")
    # The reading and warning color follow the actual level during animation.
    return replace(source, "progressBar.value", "root.progressTarget", count=4)


if __name__ == "__main__":
    print(render(Path(sys.argv[1]).read_text()), end="")
