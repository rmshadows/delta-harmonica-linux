#compdef dharm ./dharm

# Source this file, or:
#   eval "$(./dharm --show-completion-local zsh)"   # if available
#   source /path/to/delta-harmonica-linux/completions/dharm.zsh

_dharm_completion() {
  local bin="${words[1]}"
  # Prefer the token the user typed (./dharm) so completion hits the wrapper/venv.
  if [[ ! -x "$bin" ]]; then
    bin="$(command -v dharm 2>/dev/null || true)"
  fi
  if [[ -z "$bin" ]]; then
    return 1
  fi
  eval "$(env _TYPER_COMPLETE_ARGS="${words[1,$CURRENT]}" _DHARM_COMPLETE=complete_zsh "$bin")"
}

compdef _dharm_completion dharm ./dharm
