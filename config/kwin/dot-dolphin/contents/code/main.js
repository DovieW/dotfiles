let waitingForDolphin = false;

function isDolphin(window) {
    return window.desktopFileName === "org.kde.dolphin";
}

function focusDolphin(window) {
    if (!window.onAllDesktops && window.desktops.length > 0) {
        workspace.currentDesktop = window.desktops[0];
    }
    window.minimized = false;
    workspace.raiseWindow(window);
    workspace.activeWindow = window;
}

function openOrFocusDolphin() {
    const windows = workspace.stackingOrder;
    for (let index = windows.length - 1; index >= 0; index -= 1) {
        if (isDolphin(windows[index])) {
            focusDolphin(windows[index]);
            return;
        }
    }

    waitingForDolphin = true;
    callDBus(
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "StartUnit",
        "dot-dolphin-launch.service",
        "replace"
    );
}

workspace.windowAdded.connect((window) => {
    if (waitingForDolphin && isDolphin(window)) {
        waitingForDolphin = false;
        focusDolphin(window);
    }
});

registerShortcut(
    "dot-dolphin",
    "Open or Focus Dolphin",
    "Meta+E",
    openOrFocusDolphin
);
