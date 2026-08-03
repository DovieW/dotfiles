let requestedDesktop = null;

function isObsidian(window) {
    return window.desktopFileName === "obsidian";
}

function isOnDesktop(window, desktop) {
    if (window.onAllDesktops) {
        return true;
    }
    return window.desktops.some((candidate) => candidate.id === desktop.id);
}

function focusObsidian(window) {
    window.minimized = false;
    workspace.raiseWindow(window);
    workspace.activeWindow = window;
}

function manageObsidian(window) {
    if (isObsidian(window)) {
        // One dedicated launcher represents Obsidian in the taskbar. Real vault
        // windows remain available through Alt+Tab on their own desktops.
        window.skipTaskbar = true;
    }
}

function openOrFocusObsidian() {
    const desktop = workspace.currentDesktop;
    const windows = workspace.stackingOrder;
    for (let index = windows.length - 1; index >= 0; index -= 1) {
        if (isObsidian(windows[index]) && isOnDesktop(windows[index], desktop)) {
            focusObsidian(windows[index]);
            return;
        }
    }

    requestedDesktop = desktop;
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
    manageObsidian(window);
    if (requestedDesktop !== null && isObsidian(window)) {
        window.desktops = [requestedDesktop];
        workspace.currentDesktop = requestedDesktop;
        requestedDesktop = null;
        focusObsidian(window);
    }
});

workspace.stackingOrder.forEach(manageObsidian);

registerShortcut(
    "dot-obsidian",
    "Open or Focus Obsidian on This Desktop",
    "",
    openOrFocusObsidian
);
