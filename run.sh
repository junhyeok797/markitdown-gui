#!/usr/bin/env bash
# Launch MarkItDown GUI, or add/remove its app menu and desktop shortcuts.
#
#   ./run.sh              start the app (opens in your browser)
#   ./run.sh --install    add shortcuts to the app menu and the desktop
#   ./run.sh --uninstall  remove those shortcuts
set -euo pipefail

APP_DIR="$(dirname "$(readlink -f "$0")")"
cd "$APP_DIR"

APP_ID="markitdown-gui"
MENU_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/$APP_ID"
UV_INSTALL_CMD="curl -LsSf https://astral.sh/uv/install.sh | sh"

# Started from the app menu there is no terminal, so messages must go to
# desktop notifications and dialogs instead of stdout.
if [ -t 1 ]; then INTERACTIVE=1; else INTERACTIVE=0; fi

info() {
    if [ "$INTERACTIVE" = 1 ]; then
        echo "$1"
    elif command -v notify-send >/dev/null; then
        notify-send --icon="$APP_DIR/icon.png" "MarkItDown GUI" "$1" || true
    fi
}

error() {
    if [ "$INTERACTIVE" = 1 ]; then
        echo "Error: $1" >&2
    elif command -v zenity >/dev/null; then
        zenity --error --title="MarkItDown GUI" --no-wrap --text="$1" || true
    else
        info "Error: $1"
    fi
}

ask_yes_no() {
    if [ "$INTERACTIVE" = 1 ]; then
        local answer
        read -r -p "$1 [y/N] " answer
        [[ "$answer" =~ ^[Yy] ]]
    elif command -v zenity >/dev/null; then
        zenity --question --title="MarkItDown GUI" --no-wrap --text="$1"
    else
        return 1
    fi
}

find_uv() {
    # A desktop launch does not read ~/.bashrc, so uv may be missing from PATH
    # even when installed. Check the installer's default locations as well.
    local candidate
    for candidate in "$(command -v uv || true)" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

# Escape a path for use inside a quoted Exec= value (Desktop Entry spec):
# first the Exec quoting rules, then the general string escaping of backslashes.
escape_exec() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//\`/\\\`}"
    s="${s//\$/\\\$}"
    s="${s//%/%%}"
    s="${s//\\/\\\\}"
    printf '%s' "$s"
}

render_desktop_file() {
    local exec_dir line
    exec_dir="$(escape_exec "$APP_DIR")"
    while IFS= read -r line; do
        case "$line" in
            Exec=*) line="${line//__APP_DIR__/"$exec_dir"}" ;;
            *) line="${line//__APP_DIR__/"$APP_DIR"}" ;;
        esac
        printf '%s\n' "$line"
    done < "$APP_DIR/$APP_ID.desktop"
}

install_shortcuts() {
    chmod +x "$APP_DIR/run.sh"
    mkdir -p "$MENU_DIR"
    render_desktop_file > "$MENU_DIR/$APP_ID.desktop"
    chmod +x "$MENU_DIR/$APP_ID.desktop"
    update-desktop-database "$MENU_DIR" 2>/dev/null || true
    echo "Added to the app menu: $MENU_DIR/$APP_ID.desktop"

    if [ -d "$DESKTOP_DIR" ]; then
        cp "$MENU_DIR/$APP_ID.desktop" "$DESKTOP_DIR/$APP_ID.desktop"
        chmod +x "$DESKTOP_DIR/$APP_ID.desktop"
        # GNOME only runs desktop icons that are marked as trusted.
        gio set "$DESKTOP_DIR/$APP_ID.desktop" metadata::trusted true 2>/dev/null || true
        echo "Added to the desktop: $DESKTOP_DIR/$APP_ID.desktop"
    fi
    echo "If you move this folder, run './run.sh --install' again."
}

uninstall_shortcuts() {
    rm -f "$MENU_DIR/$APP_ID.desktop" "$DESKTOP_DIR/$APP_ID.desktop"
    update-desktop-database "$MENU_DIR" 2>/dev/null || true
    echo "Shortcuts removed."
}

launch() {
    local uv
    if ! uv="$(find_uv)"; then
        if ask_yes_no "MarkItDown GUI needs 'uv' to run, but it is not installed.
It can be installed with the official installer:
  $UV_INSTALL_CMD

Install uv now?"; then
            info "Installing uv..."
            if ! sh -c "$UV_INSTALL_CMD" || ! uv="$(find_uv)"; then
                error "Installing uv failed. Install it manually with:
  $UV_INSTALL_CMD"
                exit 1
            fi
        else
            error "uv is required. Install it with:
  $UV_INSTALL_CMD
Then run MarkItDown GUI again."
            exit 1
        fi
    fi

    local args=(run)
    if [ -f app.py.lock ]; then
        args+=(--locked)
    fi

    info "Starting MarkItDown GUI. It will open in your browser.
First launch may take a few minutes while dependencies are installed."

    if [ "$INTERACTIVE" = 1 ]; then
        exec "$uv" "${args[@]}" app.py
    fi

    mkdir -p "$LOG_DIR"
    local log="$LOG_DIR/launch.log"
    if ! "$uv" "${args[@]}" app.py >"$log" 2>&1; then
        error "MarkItDown GUI stopped unexpectedly.
See the log for details:
  $log"
        exit 1
    fi
}

case "${1:-}" in
    --install) install_shortcuts ;;
    --uninstall) uninstall_shortcuts ;;
    "") launch ;;
    *)
        echo "Usage: $0 [--install | --uninstall]" >&2
        exit 2
        ;;
esac
