local map = vim.keymap.set

map("n", "<Esc>", "<cmd>nohlsearch<CR>")
map("n", "<C-h>", "<C-w><C-h>", { desc = "Move to the left window" })
map("n", "<C-j>", "<C-w><C-j>", { desc = "Move to the lower window" })
map("n", "<C-k>", "<C-w><C-k>", { desc = "Move to the upper window" })
map("n", "<C-l>", "<C-w><C-l>", { desc = "Move to the right window" })

map({ "n", "v" }, "j", "v:count == 0 ? 'gj' : 'j'", { expr = true, silent = true })
map({ "n", "v" }, "k", "v:count == 0 ? 'gk' : 'k'", { expr = true, silent = true })
map("n", "n", "nzzzv")
map("n", "N", "Nzzzv")
map("n", "<C-d>", "<C-d>zz")
map("n", "<C-u>", "<C-u>zz")

map("v", "<leader>p", '"_dP', { desc = "Paste without replacing the register" })
map({ "n", "v" }, "<leader>d", '"_d', { desc = "Delete without replacing the register" })
map("n", "<leader>sR", [[:%s/\<<C-r><C-w>\>/<C-r><C-w>/gI<Left><Left><Left>]], {
  desc = "Replace the word under the cursor",
})
map("n", "<leader>x", "<cmd>silent !chmod +x %<CR>", { desc = "Make the current file executable" })
map({ "n", "x" }, "<C-Space>", function()
  vim.treesitter.select("parent")
end, { desc = "Grow Tree-sitter selection" })
map("x", "<BS>", function()
  vim.treesitter.select("child")
end, { desc = "Shrink Tree-sitter selection" })

local function session_path()
  local directory = vim.fn.stdpath("state") .. "/sessions"
  vim.fn.mkdir(directory, "p")
  return directory .. "/" .. vim.fn.sha256(vim.uv.cwd()) .. ".vim"
end

map("n", "<leader>qs", function()
  vim.cmd("mksession! " .. vim.fn.fnameescape(session_path()))
  vim.notify("Saved session for " .. vim.uv.cwd())
end, { desc = "Save project session" })
map("n", "<leader>ql", function()
  local path = session_path()
  if vim.fn.filereadable(path) == 0 then
    vim.notify("No saved session for " .. vim.uv.cwd(), vim.log.levels.WARN)
    return
  end
  vim.cmd("source " .. vim.fn.fnameescape(path))
end, { desc = "Load project session" })

map("n", "[d", function()
  vim.diagnostic.jump({ count = -1, float = true })
end, { desc = "Previous diagnostic" })
map("n", "]d", function()
  vim.diagnostic.jump({ count = 1, float = true })
end, { desc = "Next diagnostic" })
map("n", "<leader>e", vim.diagnostic.open_float, { desc = "Show diagnostic" })
map("n", "<leader>dq", vim.diagnostic.setloclist, { desc = "Diagnostic location list" })

map("n", "<leader>gg", function()
  vim.cmd("tabnew")
  vim.fn.termopen("lazygit", {
    on_exit = function()
      vim.schedule(function()
        if vim.api.nvim_buf_is_valid(0) then
          vim.cmd("tabclose")
        end
      end)
    end,
  })
end, { desc = "Lazygit" })
