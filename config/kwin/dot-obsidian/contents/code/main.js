function isObsidian(window) {
    return ["obsidian", "md.obsidian.Obsidian"].includes(window.desktopFileName);
}

function manageObsidian(window) {
    if (isObsidian(window)) {
        // Keep native Obsidian windows associated with the real pinned launcher.
        window.skipTaskbar = false;
    }
}

workspace.windowAdded.connect(manageObsidian);

workspace.stackingOrder.forEach(manageObsidian);
