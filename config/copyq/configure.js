config('maxitems', 999)
config('clipboard_mime_size_limit', 'image/.*:0;application/x-qt-image:0;.*:100M')
config('clipboard_tab', 'Clipboard')
config('tabs', ['Clipboard'])
config('hide_tabs', true)
config('hide_toolbar', false)
config('native_menu_bar', false)
config('disable_tray', true)
config('hide_main_window_in_task_bar', true)
config('close_on_unfocus', true)
config('activate_closes', true)
config('activate_focuses', true)
config('activate_pastes', true)

var managedName = 'Dotfiles Wayland paste'
var managedHistory = 'Dotfiles Clipboard History'
var retained = commands().filter(function(command) {
    return command.name !== managedName && command.name !== managedHistory
})
var managedScript = "global.dotfilesPasteVersion = 4\n" +
                    "global.dotfilesPaste = function() {\n" +
                    "  var result = execute('dot-copyq-paste')\n" +
                    "  if (!result) throw 'Could not start dot-copyq-paste'\n" +
                    "  if (result.exit_code || result.stderr) throw str(result.stderr)\n" +
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
