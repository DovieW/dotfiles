local M = {}

local directions = {
  h = "left",
  j = "down",
  k = "up",
  l = "right",
}

function M.setup()
  local pane_id = vim.env.HERDR_PANE_ID
  if not pane_id or pane_id == "" then
    return
  end

  for key, direction in pairs(directions) do
    vim.keymap.set("n", "<M-" .. key .. ">", function()
      local before = vim.api.nvim_get_current_win()
      vim.cmd("wincmd " .. key)
      if vim.api.nvim_get_current_win() == before then
        vim.fn.jobstart({
          "herdr",
          "pane",
          "focus",
          "--pane",
          pane_id,
          "--direction",
          direction,
        }, { detach = true })
      end
    end, { desc = "Navigate " .. direction })
  end
end

return M
