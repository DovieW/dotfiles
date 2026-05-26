if command -v eza >/dev/null 2>&1; then
	alias ls='eza'
	alias l='eza --oneline --classify --color=auto --icons=auto --hyperlink --all --group-directories-first'
	alias ll='l --long --modified --git'
	alias lt='ll --reverse --sort=time'
else
	alias ll='ls -hlAF --group-directories-first --color=auto'
	alias l='ls -1AFt --group-directories-first --color=auto'
	alias lt='ls -hlAFtr --group-directories-first --color=auto'
fi

if command -v bat >/dev/null 2>&1; then
	alias cat='bat --no-paging --plain'
fi

if command -v xclip >/dev/null 2>&1; then
	alias clip='xclip -selection clipboard'
elif [ -x /mnt/c/Windows/System32/clip.exe ]; then
	alias clip='/mnt/c/Windows/System32/clip.exe'
fi

alias g='git'
alias t='tmux'
alias tls='tmux ls'
alias ta='tmux attach'
alias tat='tmux attach -t'
alias c-='cd -'
alias c.='cd ..'
alias c..='cd ../..'
alias c...='cd ../../..'
