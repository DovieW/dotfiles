local opt = vim.opt

-- Keep only editing behavior that Neovim itself owns.  VS Code continues to
-- provide its own interface, completion, diagnostics, and extension commands.
opt.clipboard = "unnamedplus"
opt.ignorecase = true
opt.smartcase = true

vim.keymap.set("n", "<Esc>", "<cmd>nohlsearch<CR>", { silent = true })
