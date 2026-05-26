if [ -f "$HOME/.config/dovie-shell/aliases.sh" ]; then
	. "$HOME/.config/dovie-shell/aliases.sh"
fi

if [ -f "$HOME/.config/dovie-shell/helpers.sh" ]; then
	. "$HOME/.config/dovie-shell/helpers.sh"
fi

if command -v zoxide >/dev/null 2>&1; then
	eval "$(zoxide init "$(basename "${SHELL:-sh}")")"
fi
