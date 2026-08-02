function startUserUnit(unit) {
    callDBus(
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "StartUnit",
        unit,
        "replace"
    );
}

registerShortcut(
    "dot-copyq-history-meta",
    "Open Clipboard History (Meta+V)",
    "Meta+V",
    () => startUserUnit("dot-copyq-history.service")
);

registerShortcut(
    "dot-copyq-history-ctrl",
    "Open Clipboard History (Ctrl+Grave)",
    "Ctrl+`",
    () => startUserUnit("dot-copyq-history.service")
);

registerShortcut(
    "dot-emoji-picker",
    "Open Dotfiles Emoji Picker",
    "Meta+.",
    () => startUserUnit("dot-emoji-picker.service")
);
