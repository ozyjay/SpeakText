#!/usr/bin/env bash
set -eu

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
extension_uuid="speaktext@local"
if [ "${SPEAKTEXT_SKIP_EXTENSION_ENABLE:-0}" != "1" ] && \
        command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions disable "$extension_uuid" >/dev/null 2>&1 || true
fi
rm -f "$HOME/.local/bin/speaktext"
rm -f "$HOME/.local/libexec/speaktext/speaktext-worker"
rm -f "$data_home/applications/local.SpeakText.desktop"
rm -f "$data_home/icons/hicolor/scalable/apps/local.SpeakText.svg"
rm -f "$data_home/dbus-1/services/local.SpeakText.service"
rm -rf "$data_home/speaktext/python/speaktext"
rm -rf "$data_home/gnome-shell/extensions/$extension_uuid"
rmdir "$HOME/.local/libexec/speaktext" 2>/dev/null || true
rmdir "$data_home/speaktext/python" 2>/dev/null || true
printf 'Uninstalled SpeakText. Models, settings, and diagnostics were retained.\n'
