vim.g.mapleader = " "
vim.g.maplocalleader = " "
vim.g.have_nerd_font = true

-- VS Code owns the UI, completion UI, LSP clients, and file explorer.  Loading
-- the full terminal configuration here causes duplicate providers and makes the
-- bridge noticeably heavier than it needs to be.
if vim.g.vscode then
  require("dovie.vscode")
  return
end

require("dovie.options")
require("dovie.autocmds")
require("dovie.lazy")
require("dovie.keymaps")
