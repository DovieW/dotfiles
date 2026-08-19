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

var requestedCopyQDesktop = null;

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
    var windows = workspace.stackingOrder;
    for (var index = windows.length - 1; index >= 0; index -= 1) {
        if (isCopyQ(windows[index])) {
            focusCopyQ(windows[index]);
            return;
        }
    }
}

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
    function () { reopenUserUnit("dot-emoji-picker.service"); }
);

registerShortcut(
    "dot-clipboard-probe",
    "Verify Clipboard Shortcuts",
    "",
    function () { reopenUserUnit("dot-clipboard-probe.service"); }
);

workspace.windowAdded.connect(function (window) {
    if (requestedCopyQDesktop !== null && isCopyQ(window)) {
        focusCopyQ(window);
    }
});
