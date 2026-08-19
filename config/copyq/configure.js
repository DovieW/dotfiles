config('maxitems', 1100)
config('clipboard_mime_size_limit', '.*:100M')
config('clipboard_tab', 'Clipboard')
config('tabs', ['Clipboard'])
config('hide_tabs', true)
config('hide_toolbar', false)
config('native_menu_bar', false)
config('disable_tray', true)
config('hide_main_window_in_task_bar', false)
config('close_on_unfocus', false)
config('activate_closes', true)
config('activate_focuses', true)
config('activate_pastes', true)
config('autostart', false)

var managedName = 'Dotfiles Wayland paste'
var managedHistory = 'Dotfiles Clipboard History'
var managedBin = str(env('XDG_BIN_HOME'))
if (!managedBin) managedBin = str(env('HOME')) + '/.local/bin'
var managedPasteHelper = managedBin + '/dot-copyq-paste'
var retained = commands().filter(function(command) {
    return command.name !== managedName && command.name !== managedHistory
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
setCommands(retained)

// setCommands() persists script commands but does not load them into the
// already-running server. Apply this one immediately without restarting CopyQ
// and killing its clipboard helpers, which CopyQ reports as exit-code alerts.
var managedScriptResult = eval(managedScript)
