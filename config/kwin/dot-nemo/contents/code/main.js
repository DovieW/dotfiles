let waitingForNemo = false;

function isNemo(window) {
    return window.desktopFileName === "nemo"
        || window.desktopFileName === "org.Nemo"
        || String(window.resourceClass).toLowerCase() === "nemo";
}

function focusNemo(window) {
    if (!window.onAllDesktops && window.desktops.length > 0) {
        workspace.currentDesktop = window.desktops[0];
    }
    window.minimized = false;
    workspace.raiseWindow(window);
    workspace.activeWindow = window;
}

function openOrFocusNemo() {
    const windows = workspace.stackingOrder;
    for (let index = windows.length - 1; index >= 0; index -= 1) {
        if (isNemo(windows[index])) {
            focusNemo(windows[index]);
            return;
        }
    }

    waitingForNemo = true;
    callDBus(
        "org.freedesktop.systemd1",
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "StartUnit",
        "dot-nemo-launch.service",
        "replace"
    );
}

workspace.windowAdded.connect((window) => {
    if (waitingForNemo && isNemo(window)) {
        waitingForNemo = false;
        focusNemo(window);
    }
});

registerShortcut(
    "dot-nemo",
    "Open or Focus Nemo",
    "Meta+E",
    openOrFocusNemo
);
