function reopenFlameshot() {
    callDBus(
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "RestartUnit",
        "dot-flameshot-capture.service",
        "replace"
    );
}

registerShortcut(
    "dot-flameshot-capture",
    "Open Flameshot Capture",
    "Print",
    reopenFlameshot
);
