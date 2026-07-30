local group = vim.api.nvim_create_augroup("dovie-defaults", { clear = true })

vim.api.nvim_create_autocmd("TextYankPost", {
  group = group,
  desc = "Highlight yanked text",
  callback = function()
    vim.highlight.on_yank()
  end,
})

vim.api.nvim_create_autocmd("BufReadPost", {
  group = group,
  desc = "Return to the last edit position",
  callback = function(args)
    local mark = vim.api.nvim_buf_get_mark(args.buf, '"')
    local line_count = vim.api.nvim_buf_line_count(args.buf)
    if mark[1] > 0 and mark[1] <= line_count then
      pcall(vim.api.nvim_win_set_cursor, 0, mark)
    end
  end,
})

vim.api.nvim_create_autocmd("FileType", {
  group = group,
  desc = "Keep comments from continuing automatically",
  callback = function()
    vim.opt_local.formatoptions:remove({ "c", "r", "o" })
  end,
})

vim.api.nvim_create_autocmd("TermOpen", {
  group = group,
  desc = "Use a clean terminal buffer",
  callback = function()
    vim.opt_local.number = false
    vim.opt_local.relativenumber = false
    vim.cmd.startinsert()
  end,
})

vim.api.nvim_create_autocmd("VimEnter", {
  group = group,
  desc = "Open Oil for an empty invocation or directory",
  callback = function()
    if vim.g.dovie_headless or #vim.api.nvim_list_uis() == 0 then
      return
    end
    local argument = vim.fn.argv(0)
    if vim.fn.argc() == 0 or (argument ~= "" and vim.fn.isdirectory(argument) == 1) then
      vim.schedule(function()
        require("oil").open(argument ~= "" and argument or nil)
      end)
    end
  end,
})
