var managedOptions = {
    maxitems: 1100,
    clipboard_mime_size_limit: 'text/uri-list.*:512K;(text/html|text/rtf|application/rtf).*:2M;text/.*:1M;image/.*:25M;.*:4M',
    clipboard_tab: 'Clipboard',
    hide_tabs: false,
    save_filter_history: true,
    show_simple_items: true,
    text_wrap: false,
    navigation_style: 1, // Vi
    hide_toolbar: false,
    native_menu_bar: false,
    disable_tray: true,
    hide_main_window_in_task_bar: false,
    close_on_unfocus: false,
    activate_closes: true,
    activate_focuses: true,
    activate_pastes: true,
    autostart: false
}
var starterTabsSeeded = 'dotfiles/CopyQStarterTabsSeeded'

function configureCopyQ(modeOrHelper) {
    if (modeOrHelper === '--check') {
        Object.keys(managedOptions).forEach(function(key) {
            if (str(config(key)) !== String(managedOptions[key]))
                throw new Error('CopyQ clipboard setting drifted: ' + key)
        })
        if (tab().indexOf('Clipboard') < 0 || !settings(starterTabsSeeded))
            throw new Error('CopyQ clipboard tab setup is incomplete.')
        return
    }

    Object.keys(managedOptions).forEach(function(key) {
        config(key, managedOptions[key])
    })
    if (!settings(starterTabsSeeded)) {
        var tabs = tab()
        var starterTabs = ['Clipboard', 'Snippets', 'Prompts', 'Notes']
        starterTabs.forEach(function(name) {
            if (tabs.indexOf(name) < 0)
                tabs.push(name)
        })
        config('tabs', tabs)
        settings(starterTabsSeeded, true)
    }
    installManagedCommands(modeOrHelper)
}

function installManagedCommands(managedStageHelper) {
    var managedName = 'Dotfiles Wayland paste'
    var managedHistory = 'Dotfiles Clipboard History'
    var managedStage = 'Dotfiles stage clipboard images'
    var managedBin = str(env('XDG_BIN_HOME'))
    if (!managedBin) managedBin = str(env('HOME')) + '/.local/bin'
    var managedPasteHelper = managedBin + '/dot-copyq-paste'
    var retained = commands().filter(function(command) {
        return command.name !== managedName && command.name !== managedHistory && command.name !== managedStage
    })
    var managedScript = "global.dotfilesPasteVersion = 5\n" +
                        "global.dotfilesPasteHelper = " + JSON.stringify(managedPasteHelper) + "\n" +
                        "global.dotfilesPaste = function() {\n" +
                        "  var result = execute(global.dotfilesPasteHelper, '--paste')\n" +
                        "  if (!result) {\n" +
                        "    popup('CopyQ paste failed', 'Could not start ' + global.dotfilesPasteHelper)\n" +
                        "    return\n" +
                        "  }\n" +
                        "  if (result.exit_code) {\n" +
                        "    var message = str(result.stderr).trim() || ('Paste helper exited ' + result.exit_code)\n" +
                        "    serverLog('CopyQ paste failed: ' + message)\n" +
                        "    popup('CopyQ paste failed', message)\n" +
                        "  }\n" +
                        "}\n" +
                        "Object.defineProperty(global, 'paste', {\n" +
                        "  value: global.dotfilesPaste,\n" +
                        "  writable: true,\n" +
                        "  configurable: true\n" +
                        "})\n"
    retained.push({
        name: managedName,
        isScript: true,
        cmd: managedScript
    })
    retained.push({
        name: managedStage,
        automatic: true,
        cmd: "copyq:\n" +
             "if (isClipboard()) {\n" +
             "  var images = dataFormats().filter(function(m) { return m.indexOf('image/') === 0; });\n" +
             "  if (images.length) {\n" +
             "    var mime = images.indexOf('image/png') >= 0 ? 'image/png' : images[0];\n" +
             "    try {\n" +
             "      var staged = execute(" + JSON.stringify(managedStageHelper) + ", '--stage', null, data(mime));\n" +
             "      if (!staged || staged.exit_code) serverLog('Image path staging failed');\n" +
             "    } catch (error) {\n" +
             "      serverLog('Image path staging failed: ' + error.message);\n" +
             "    }\n" +
             "  }\n" +
             "}\n"
    })
    setCommands(retained)

    // setCommands() persists script commands but does not load them into the
    // already-running server. Apply this one immediately without restarting CopyQ
    // and killing its clipboard helpers, which CopyQ reports as exit-code alerts.
    var managedScriptResult = eval(managedScript)
}

configureCopyQ(str(arguments[1]))
