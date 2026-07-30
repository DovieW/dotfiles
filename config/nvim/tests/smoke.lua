vim.g.dovie_headless = true

local required = {
  "lazy",
  "fzf-lua",
  "oil",
  "gitsigns",
  "conform",
  "lint",
  "blink.cmp",
  "nvim-treesitter",
}

for _, module in ipairs(required) do
  local ok, error_message = pcall(require, module)
  assert(ok, ("could not load %s: %s"):format(module, error_message))
end

require("lazy").load({ plugins = { "nvim-lspconfig" } })
assert(vim.lsp.is_enabled("lua_ls"), "Lua LSP configuration is not enabled")

assert(vim.g.mapleader == " ", "space is not the leader")
assert(vim.o.undofile, "persistent undo is not enabled")
assert(vim.o.clipboard:find("unnamedplus"), "system clipboard is not enabled")
assert(vim.fn.maparg("-", "n") ~= "", "Oil mapping is missing")
assert(vim.fn.maparg("<leader>sf", "n") ~= "", "fzf-lua file mapping is missing")
assert(vim.fn.maparg("<leader>gg", "n") ~= "", "Lazygit mapping is missing")
assert(vim.fn.maparg("<C-Space>", "n") ~= "", "Tree-sitter selection mapping is missing")
assert(vim.fn.maparg("<leader>qs", "n") ~= "", "Session save mapping is missing")
assert(pcall(vim.treesitter.language.add, "lua"), "Lua Tree-sitter parser is unavailable")

print("Neovim smoke test passed")
