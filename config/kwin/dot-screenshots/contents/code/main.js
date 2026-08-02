function restartUnit(unit) {
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
    "dot-flameshot-region-clipboard",
    "Copy Rectangular Screenshot",
    "Meta+Shift+S",
    function () { restartUnit("dot-flameshot-region-clipboard.service"); }
);

registerShortcut(
    "dot-flameshot-full-clipboard",
    "Copy Full Screen Screenshot",
    "Print",
    function () { restartUnit("dot-flameshot-full-clipboard.service"); }
);

registerShortcut(
    "dot-active-window-clipboard",
    "Copy Active Window Screenshot",
    "Alt+Print",
    function () { restartUnit("dot-active-window-clipboard.service"); }
);

registerShortcut(
    "dot-flameshot-region-pin",
    "Pin Rectangular Screenshot",
    "Meta+Ctrl+Shift+S",
    function () { restartUnit("dot-flameshot-region-pin.service"); }
);
