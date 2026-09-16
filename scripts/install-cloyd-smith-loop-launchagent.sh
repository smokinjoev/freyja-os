#!/usr/bin/env sh
set -eu

repo="${FREYJA_REPO:-/Users/freyja/freyja-os}"
label="com.freyja-os.cloyd-smith-loop"
source_plist="$repo/scripts/$label.plist"
target_dir="$HOME/Library/LaunchAgents"
target_plist="$target_dir/$label.plist"

mkdir -p "$target_dir" "$repo/logs" "$HOME/.local/state/freyja"
cp "$source_plist" "$target_plist"

if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)" "$target_plist" >/dev/null 2>&1 || true
fi

launchctl bootstrap "gui/$(id -u)" "$target_plist"
launchctl enable "gui/$(id -u)/$label"
launchctl kickstart -k "gui/$(id -u)/$label"

"$repo/scripts/status-cloyd-smith-loop.sh"
