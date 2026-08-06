#!/usr/bin/env bash
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
bin_dir="$HOME/.local/bin"
libexec_dir="$HOME/.local/libexec/speaktext"
python_dir="$data_home/speaktext/python"
applications_dir="$data_home/applications"
icons_dir="$data_home/icons/hicolor/scalable/apps"

if [ ! -x "$project_dir/build/speaktext-worker" ]; then
    printf 'Native worker is missing; run scripts/bootstrap.sh first.\n' >&2
    exit 1
fi

install -d "$bin_dir" "$libexec_dir" "$python_dir" "$applications_dir" "$icons_dir"
install -m 0755 "$project_dir/scripts/speaktext-launcher" "$bin_dir/speaktext"
install -m 0755 "$project_dir/build/speaktext-worker" "$libexec_dir/speaktext-worker"
install -d "$python_dir/speaktext"
install -m 0644 "$project_dir"/src/speaktext/*.py "$python_dir/speaktext/"
install -m 0644 "$project_dir/data/local.SpeakText.svg" "$icons_dir/local.SpeakText.svg"
sed "s|@EXEC@|$bin_dir/speaktext|" "$project_dir/data/local.SpeakText.desktop.in" \
    > "$applications_dir/local.SpeakText.desktop"
chmod 0644 "$applications_dir/local.SpeakText.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
fi
printf 'Installed SpeakText for the current user. Run: %s/speaktext\n' "$bin_dir"
