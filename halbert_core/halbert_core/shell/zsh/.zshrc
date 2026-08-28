# Halbert shell integration — sourced via ZDOTDIR=<halbert>/shell/zsh zsh
# Source the user's real zshrc first.
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc"
__halbert_precmd() {
    local ec=$?
    printf '\e]133;A\a'
    printf '\e]133;D;%d\a' "$ec"
}
__halbert_preexec() {
    printf '\e]133;B\a'
    printf '\e]7;file://%s%s\a' "$(hostname)" "$PWD"
    local id="$$-$(date +%s%N 2>/dev/null || date +%s)"
    local cmd_b64=$(echo -n "$1" | base64)
    printf '\e]133;C;id=%s;cmd=%s\a' "$id" "$cmd_b64"
}
precmd_functions=(__halbert_precmd $precmd_functions)
preexec_functions=(__halbert_preexec $preexec_functions)
