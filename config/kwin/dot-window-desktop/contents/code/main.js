function desktopIndex(desktop) {
    const desktops = workspace.desktops;
    for (let index = 0; index < desktops.length; index += 1) {
        if (desktops[index].id === desktop.id) {
            return index;
        }
    }
    return -1;
}

function isTeams(window) {
    return window.desktopFileName === "teams-for-linux"
        || window.resourceClass === "teams-for-linux";
}

function suppressTeamsAttention(window) {
    if (!isTeams(window)) {
        return;
    }
    window.demandsAttention = false;
    window.demandsAttentionChanged.connect(() => {
        if (window.demandsAttention) {
            window.demandsAttention = false;
        }
    });
}

function moveWindowAndFollow(offset) {
    const window = workspace.activeWindow;
    if (!window || window.onAllDesktops) {
        return;
    }

    const desktops = workspace.desktops;
    const currentIndex = desktopIndex(workspace.currentDesktop);
    const targetIndex = currentIndex + offset;
    if (currentIndex < 0 || targetIndex < 0 || targetIndex >= desktops.length) {
        return;
    }

    const targetDesktop = desktops[targetIndex];
    window.desktops = [targetDesktop];
    workspace.currentDesktop = targetDesktop;
    workspace.raiseWindow(window);
    workspace.activeWindow = window;
}

registerShortcut(
    "dot-window-desktop-left",
    "Move Window and Follow Left",
    "Meta+Alt+Left",
    () => moveWindowAndFollow(-1)
);

registerShortcut(
    "dot-window-desktop-right",
    "Move Window and Follow Right",
    "Meta+Alt+Right",
    () => moveWindowAndFollow(1)
);

workspace.windowAdded.connect(suppressTeamsAttention);
workspace.stackingOrder.forEach(suppressTeamsAttention);
