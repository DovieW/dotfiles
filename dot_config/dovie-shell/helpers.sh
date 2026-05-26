groot() {
	cd "$(git rev-parse --show-toplevel 2>/dev/null)" || return
}

v() {
	if [ -n "${V_EDITOR:-}" ]; then
		"$V_EDITOR" "$@"
	elif command -v nvim >/dev/null 2>&1; then
		nvim "$@"
	elif command -v vim >/dev/null 2>&1; then
		vim "$@"
	else
		nano "$@"
	fi
}

cclip() {
	if command -v xclip >/dev/null 2>&1; then
		xclip -selection clipboard < "$1"
	elif command -v clip >/dev/null 2>&1; then
		clip < "$1"
	else
		printf 'No clipboard command found.\n' >&2
		return 1
	fi
}

search() {
	if ! command -v fzf >/dev/null 2>&1 || ! command -v fd >/dev/null 2>&1; then
		printf 'search requires fd and fzf.\n' >&2
		return 1
	fi

	local selection
	selection=$(fd --hidden --type f --type d | fzf --preview '([ -d {} ] && printf "directory\n" || bat -n --color=always {} 2>/dev/null)' --preview-window=right:40%)
	[ -n "$selection" ] || return 0

	if [ -f "$selection" ]; then
		v "$selection"
	elif [ -d "$selection" ]; then
		cd "$selection" || return
	fi
}
