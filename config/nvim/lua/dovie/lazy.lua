local lazy_path = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not vim.uv.fs_stat(lazy_path) then
  local output = vim.fn.system({
    "git",
    "clone",
    "--filter=blob:none",
    "--branch=stable",
    "https://github.com/folke/lazy.nvim.git",
    lazy_path,
  })
  if vim.v.shell_error ~= 0 then
    error("Could not install lazy.nvim:\n" .. output)
  end
end

vim.opt.rtp:prepend(lazy_path)

require("lazy").setup({
  spec = { { import = "dovie.plugins" } },
  defaults = { lazy = true, version = false },
  checker = { enabled = false },
  change_detection = { notify = false },
  install = { colorscheme = { "github_dark_default", "habamax" } },
  rocks = { enabled = false },
  ui = { border = "rounded" },
})
