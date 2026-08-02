function reopenUserUnit(unit) {
    callDBus(
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "RestartUnit",
        unit,
        "replace"
    );
}

registerShortcut(
    "dot-copyq-history-meta",
    "Open Clipboard History (Meta+V)",
    "Meta+V",
    () => reopenUserUnit("dot-copyq-history.service")
);

registerShortcut(
    "dot-copyq-history-ctrl",
    "Open Clipboard History (Ctrl+Grave)",
    "Ctrl+`",
    () => reopenUserUnit("dot-copyq-history.service")
);

registerShortcut(
    "dot-emoji-picker",
    "Open Dotfiles Emoji Picker",
    "Meta+.",
    () => reopenUserUnit("dot-emoji-picker.service")
);
