let waitingForObsidian = false;

function isObsidian(window) {
    return window.desktopFileName === "obsidian"
        && window.caption.toLowerCase() !== "obsidian";
}

function focusObsidian(window) {
    if (!window.onAllDesktops && window.desktops.length > 0) {
        workspace.currentDesktop = window.desktops[0];
    }
    window.minimized = false;
    workspace.raiseWindow(window);
    workspace.activeWindow = window;
}

function openOrFocusObsidian() {
    const windows = workspace.stackingOrder;
    for (let index = windows.length - 1; index >= 0; index -= 1) {
        if (isObsidian(windows[index])) {
            focusObsidian(windows[index]);
            return;
        }
    }

    waitingForObsidian = true;
    callDBus(
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "StartUnit",
        "dot-obsidian-launch.service",
        "replace"
    );
}

workspace.windowAdded.connect((window) => {
    if (waitingForObsidian && isObsidian(window)) {
        waitingForObsidian = false;
        focusObsidian(window);
    }
});

registerShortcut(
    "dot-obsidian",
    "Open or Focus Obsidian",
    "",
    openOrFocusObsidian
);
