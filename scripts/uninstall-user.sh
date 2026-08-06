#!/usr/bin/env bash
set -eu

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
rm -f "$HOME/.local/bin/speaktext"
rm -f "$HOME/.local/libexec/speaktext/speaktext-worker"
rm -f "$data_home/applications/local.SpeakText.desktop"
rm -f "$data_home/icons/hicolor/scalable/apps/local.SpeakText.svg"
rm -rf "$data_home/speaktext/python/speaktext"
rmdir "$HOME/.local/libexec/speaktext" 2>/dev/null || true
rmdir "$data_home/speaktext/python" 2>/dev/null || true
printf 'Uninstalled SpeakText. Models, settings, and diagnostics were retained.\n'

