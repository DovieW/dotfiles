local function git_root()
  local result = vim.fs.root(0, ".git")
  return result or vim.uv.cwd()
end

return {
  {
    "projekt0n/github-nvim-theme",
    lazy = false,
    priority = 1000,
    config = function()
      require("github-theme").setup({
        options = {
          transparent = false,
          terminal_colors = true,
          dim_inactive = false,
        },
      })
      vim.cmd.colorscheme("github_dark_default")

      -- Keep the current line visible without the conspicuous slate band of
      -- the stock GitHub theme.
      local function soften_cursor_line()
        vim.api.nvim_set_hl(0, "CursorLine", { bg = "#0f141a" })
      end
      soften_cursor_line()
      vim.api.nvim_create_autocmd("ColorScheme", {
        group = vim.api.nvim_create_augroup("dovie-soft-cursorline", { clear = true }),
        callback = soften_cursor_line,
      })
    end,
  },
  {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-mini/mini.nvim" },
    opts = {
      options = {
        theme = "auto",
        component_separators = "",
        section_separators = "",
        globalstatus = true,
      },
    },
  },
  {
    "folke/which-key.nvim",
    event = "VeryLazy",
    opts = {
      preset = "modern",
      delay = 350,
      spec = {
        { "<leader>c", group = "Code" },
        { "<leader>d", group = "Diagnostics/delete" },
        { "<leader>f", group = "File/format" },
        { "<leader>g", group = "Git" },
        { "<leader>h", group = "Hunks" },
        { "<leader>o", group = "Obsidian" },
        { "<leader>q", group = "Session/quit" },
        { "<leader>s", group = "Search" },
        { "<leader>t", group = "Toggle/trouble" },
      },
    },
  },
  {
    "nvim-mini/mini.nvim",
    version = false,
    lazy = false,
    config = function()
      require("mini.icons").setup()
      MiniIcons.mock_nvim_web_devicons()
      require("mini.pairs").setup()
      require("mini.surround").setup()
    end,
  },
  {
    "ibhagwan/fzf-lua",
    cmd = "FzfLua",
    dependencies = { "nvim-mini/mini.nvim" },
    keys = {
      { "<leader><space>", "<cmd>FzfLua buffers sort_mru=true sort_lastused=true<CR>", desc = "Buffers" },
      { "<leader>?", "<cmd>FzfLua oldfiles<CR>", desc = "Recent files" },
      { "<leader>gf", "<cmd>FzfLua git_files<CR>", desc = "Git files" },
      { "<leader>sf", "<cmd>FzfLua files hidden=true<CR>", desc = "Files" },
      { "<leader>sg", "<cmd>FzfLua live_grep<CR>", desc = "Live grep" },
      {
        "<leader>sG",
        function()
          require("fzf-lua").live_grep({ cwd = git_root() })
        end,
        desc = "Live grep Git root",
      },
      { "<leader>sw", "<cmd>FzfLua grep_cword<CR>", desc = "Current word" },
      { "<leader>sb", "<cmd>FzfLua buffers<CR>", desc = "Buffers" },
      { "<leader>sr", "<cmd>FzfLua resume<CR>", desc = "Resume search" },
      { '<leader>s"', "<cmd>FzfLua registers<CR>", desc = "Registers" },
      { "<leader>sh", "<cmd>FzfLua helptags<CR>", desc = "Help" },
      { "<leader>sd", "<cmd>FzfLua diagnostics_document<CR>", desc = "Document diagnostics" },
      { "<leader>ss", "<cmd>FzfLua builtin<CR>", desc = "Search pickers" },
      { "<leader>s/", "<cmd>FzfLua lgrep_curbuf<CR>", desc = "Search current buffer" },
    },
    opts = {
      fzf_opts = {
        ["--layout"] = "reverse-list",
        ["--highlight-line"] = true,
        ["--info"] = "inline-right",
        ["--pointer"] = "›",
        ["--marker"] = "●",
      },
      winopts = {
        height = 0.88,
        width = 0.9,
        border = "rounded",
        title = " FZF ",
        title_pos = "center",
        preview = {
          layout = "flex",
          border = "border",
          title = " Preview ",
          title_pos = "center",
        },
      },
      files = {
        git_icons = true,
        file_icons = true,
        color_icons = true,
      },
    },
  },
  {
    "stevearc/oil.nvim",
    cmd = "Oil",
    keys = { { "-", "<cmd>Oil<CR>", desc = "Parent directory" } },
    opts = {
      default_file_explorer = true,
      delete_to_trash = true,
      skip_confirm_for_simple_edits = true,
      view_options = {
        show_hidden = true,
        is_always_hidden = function(name)
          return name == ".git" or name == ".."
        end,
      },
      float = { padding = 4, border = "rounded" },
    },
  },
  {
    "ThePrimeagen/harpoon",
    branch = "harpoon2",
    dependencies = { "nvim-lua/plenary.nvim" },
    keys = function()
      local harpoon = require("harpoon")
      return {
        {
          "<leader>ha",
          function()
            harpoon:list():add()
          end,
          desc = "Add Harpoon file",
        },
        {
          "<leader>hm",
          function()
            harpoon.ui:toggle_quick_menu(harpoon:list())
          end,
          desc = "Harpoon menu",
        },
        {
          "<leader>h1",
          function()
            harpoon:list():select(1)
          end,
          desc = "Harpoon file 1",
        },
        {
          "<leader>h2",
          function()
            harpoon:list():select(2)
          end,
          desc = "Harpoon file 2",
        },
        {
          "<leader>h3",
          function()
            harpoon:list():select(3)
          end,
          desc = "Harpoon file 3",
        },
        {
          "<leader>h4",
          function()
            harpoon:list():select(4)
          end,
          desc = "Harpoon file 4",
        },
      }
    end,
    config = function()
      require("harpoon"):setup()
    end,
  },
  {
    "lewis6991/gitsigns.nvim",
    event = { "BufReadPre", "BufNewFile" },
    opts = {
      on_attach = function(buf)
        local gs = require("gitsigns")
        local function map(mode, lhs, rhs, desc)
          vim.keymap.set(mode, lhs, rhs, { buffer = buf, desc = desc })
        end
        map("n", "]h", function()
          gs.nav_hunk("next")
        end, "Next hunk")
        map("n", "[h", function()
          gs.nav_hunk("prev")
        end, "Previous hunk")
        map("n", "<leader>hs", gs.stage_hunk, "Stage hunk")
        map("n", "<leader>hr", gs.reset_hunk, "Reset hunk")
        map("n", "<leader>hS", gs.stage_buffer, "Stage buffer")
        map("n", "<leader>hu", gs.undo_stage_hunk, "Undo staged hunk")
        map("n", "<leader>hR", gs.reset_buffer, "Reset buffer")
        map("v", "<leader>hs", function()
          gs.stage_hunk({ vim.fn.line("."), vim.fn.line("v") })
        end, "Stage hunk")
        map("v", "<leader>hr", function()
          gs.reset_hunk({ vim.fn.line("."), vim.fn.line("v") })
        end, "Reset hunk")
        map("n", "<leader>hp", gs.preview_hunk, "Preview hunk")
        map("n", "<leader>hb", gs.blame_line, "Blame line")
        map("n", "<leader>hd", gs.diffthis, "Diff file")
        map("n", "<leader>hD", function()
          gs.diffthis("~")
        end, "Diff against previous revision")
        map("n", "<leader>tb", gs.toggle_current_line_blame, "Toggle line blame")
        map("n", "<leader>td", gs.toggle_deleted, "Toggle deleted lines")
        map({ "o", "x" }, "ih", gs.select_hunk, "Select hunk")
      end,
    },
  },
  {
    "sindrets/diffview.nvim",
    cmd = { "DiffviewOpen", "DiffviewFileHistory" },
    keys = {
      { "<leader>gd", "<cmd>DiffviewOpen<CR>", desc = "Diff view" },
      { "<leader>gh", "<cmd>DiffviewFileHistory %<CR>", desc = "File history" },
    },
  },
  {
    "folke/trouble.nvim",
    cmd = "Trouble",
    opts = {},
    keys = {
      { "<leader>tt", "<cmd>Trouble diagnostics toggle<CR>", desc = "Diagnostics" },
      { "<leader>tq", "<cmd>Trouble qflist toggle<CR>", desc = "Quickfix" },
      { "<leader>tl", "<cmd>Trouble loclist toggle<CR>", desc = "Location list" },
    },
  },
  {
    "mbbill/undotree",
    cmd = "UndotreeToggle",
    keys = { { "<leader>u", "<cmd>UndotreeToggle<CR>", desc = "Undo tree" } },
  },
  {
    "christoomey/vim-tmux-navigator",
    lazy = false,
    init = function()
      vim.g.tmux_navigator_no_mappings = 1
    end,
    keys = {
      { "<M-h>", "<cmd>TmuxNavigateLeft<CR>", desc = "Navigate left" },
      { "<M-j>", "<cmd>TmuxNavigateDown<CR>", desc = "Navigate down" },
      { "<M-k>", "<cmd>TmuxNavigateUp<CR>", desc = "Navigate up" },
      { "<M-l>", "<cmd>TmuxNavigateRight<CR>", desc = "Navigate right" },
    },
  },
  {
    "okuuva/auto-save.nvim",
    event = { "InsertLeave", "TextChanged" },
    opts = {
      enabled = true,
      trigger_events = {
        immediate_save = { "BufLeave", "FocusLost" },
        defer_save = { "InsertLeave", "TextChanged" },
        cancel_deferred_save = { "InsertEnter" },
      },
      condition = function(buf)
        local excluded = {
          [""] = false,
          gitcommit = true,
          gitrebase = true,
          help = true,
          lazy = true,
          oil = true,
          prompt = true,
          qf = true,
          terminal = true,
        }
        return vim.bo[buf].modifiable
          and not vim.bo[buf].readonly
          and vim.bo[buf].buftype == ""
          and not excluded[vim.bo[buf].filetype]
          and vim.api.nvim_buf_get_name(buf) ~= ""
      end,
      debounce_delay = 1000,
    },
  },
  {
    "nvim-treesitter/nvim-treesitter",
    branch = "main",
    lazy = false,
    build = ":TSUpdate",
    config = function()
      local parsers = {
        "bash",
        "css",
        "diff",
        "dockerfile",
        "git_config",
        "git_rebase",
        "gitattributes",
        "gitcommit",
        "gitignore",
        "html",
        "javascript",
        "jsdoc",
        "json",
        "json5",
        "lua",
        "luadoc",
        "markdown",
        "markdown_inline",
        "python",
        "query",
        "sql",
        "toml",
        "tsx",
        "typescript",
        "vim",
        "vimdoc",
        "yaml",
      }
      local installation = require("nvim-treesitter").install(parsers)
      if #vim.api.nvim_list_uis() == 0 then
        installation:wait(300000)
      end
      vim.api.nvim_create_autocmd("FileType", {
        group = vim.api.nvim_create_augroup("dovie-treesitter", { clear = true }),
        callback = function(args)
          local language = vim.treesitter.language.get_lang(vim.bo[args.buf].filetype)
          if language and pcall(vim.treesitter.start, args.buf, language) then
            vim.wo.foldexpr = "v:lua.vim.treesitter.foldexpr()"
            vim.wo.foldmethod = "expr"
            vim.wo.foldlevel = 99
            if vim.treesitter.query.get(language, "indents") then
              vim.bo[args.buf].indentexpr = "v:lua.require'nvim-treesitter'.indentexpr()"
            end
          end
        end,
      })
    end,
  },
  {
    "epwalsh/obsidian.nvim",
    version = "*",
    ft = "markdown",
    dependencies = { "nvim-lua/plenary.nvim" },
    opts = function()
      local workspaces = {}
      local vault_root = vim.fn.expand("~/repos/Obsidian")
      for _, path in ipairs(vim.fn.globpath(vault_root, "*", false, true)) do
        if vim.fn.isdirectory(path .. "/.obsidian") == 1 then
          table.insert(workspaces, { name = vim.fn.fnamemodify(path, ":t"), path = path })
        end
      end
      return {
        workspaces = workspaces,
        completion = { nvim_cmp = false, min_chars = 2 },
        picker = { name = "fzf-lua" },
        ui = { enable = false },
        new_notes_location = "current_dir",
        disable_frontmatter = true,
      }
    end,
    keys = {
      { "<leader>oo", "<cmd>ObsidianOpen<CR>", desc = "Open in Obsidian" },
      { "<leader>os", "<cmd>ObsidianSearch<CR>", desc = "Search notes" },
      { "<leader>oq", "<cmd>ObsidianQuickSwitch<CR>", desc = "Switch note" },
      { "<leader>on", "<cmd>ObsidianNew<CR>", desc = "New note" },
      { "<leader>ob", "<cmd>ObsidianBacklinks<CR>", desc = "Backlinks" },
    },
  },
  { import = "dovie.plugins.lsp" },
}
