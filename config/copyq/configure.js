config('maxitems', 999)
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
retained.push({
    name: managedName,
    isScript: true,
    cmd: "global.paste = function() {\n" +
         "  var result = execute('dot-copyq-paste')\n" +
         "  if (!result) throw 'Could not start dot-copyq-paste'\n" +
         "  if (result.exit_code || result.stderr) throw str(result.stderr)\n" +
         "}\n"
})
retained.push({
    name: managedHistory,
    cmd: 'copyq: show("Clipboard")',
    globalShortcuts: ['meta+v'],
    isGlobalShortcut: true
})
setCommands(retained)
