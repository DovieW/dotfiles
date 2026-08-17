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

let requestedCopyQDesktop = null;

function isCopyQ(window) {
    return window.resourceClass === "com.github.hluk.copyq" ||
        window.desktopFileName === "com.github.hluk.copyq";
}

function focusCopyQ(window) {
    if (requestedCopyQDesktop !== null) {
        window.desktops = [requestedCopyQDesktop];
        workspace.currentDesktop = requestedCopyQDesktop;
        requestedCopyQDesktop = null;
    }
    window.minimized = false;
    workspace.raiseWindow(window);
    workspace.activeWindow = window;
}

function openCopyQ() {
    requestedCopyQDesktop = workspace.currentDesktop;
    reopenUserUnit("dot-copyq-history.service");
    const windows = workspace.stackingOrder;
    for (let index = windows.length - 1; index >= 0; index -= 1) {
        if (isCopyQ(windows[index])) {
            focusCopyQ(windows[index]);
            return;
        }
    }
}

workspace.windowAdded.connect((window) => {
    if (requestedCopyQDesktop !== null && isCopyQ(window)) {
        focusCopyQ(window);
    }
});

registerShortcut(
    "dot-copyq-history-meta",
    "Open Clipboard History (Meta+V)",
    "Meta+V",
    openCopyQ
);

registerShortcut(
    "dot-copyq-history-ctrl",
    "Open Clipboard History (Ctrl+Grave)",
    "Ctrl+`",
    openCopyQ
);

registerShortcut(
    "dot-emoji-picker",
    "Open Dotfiles Emoji Picker",
    "Meta+.",
    () => reopenUserUnit("dot-emoji-picker.service")
);
