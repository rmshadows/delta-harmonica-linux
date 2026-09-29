#compdef dharm ./dharm

# Prefer:  source ./activate   (repo root; per-terminal, no zshrc)
# Or source this file directly.

_dharm_completion() {
  local bin="${words[1]}"
  # Resolve relative ./dharm against the caller's cwd.
  if [[ "$bin" == ./* || "$bin" == ../* ]]; then
    bin="${bin:a}"
  fi
  if [[ ! -x "$bin" ]]; then
    bin="$(command -v dharm 2>/dev/null || true)"
  fi
  if [[ -z "$bin" || ! -x "$bin" ]]; then
    return 1
  fi
  # Quoted eval keeps Typer's multiline _arguments spec intact.
  eval "$(env _TYPER_COMPLETE_ARGS="${words[1,$CURRENT]}" _DHARM_COMPLETE=complete_zsh "$bin")"
}

compdef _dharm_completion dharm ./dharm
