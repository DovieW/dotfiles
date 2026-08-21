function isObsidian(window) {
    return ["obsidian", "md.obsidian.Obsidian"].includes(window.desktopFileName);
}

function manageObsidian(window) {
    if (isObsidian(window)) {
        // One dedicated launcher represents Obsidian in the taskbar. Real vault
        // windows remain available through Alt+Tab on their own desktops.
        window.skipTaskbar = true;
    }
}

workspace.windowAdded.connect(manageObsidian);

workspace.stackingOrder.forEach(manageObsidian);
