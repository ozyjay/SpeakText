#!/usr/bin/env bash
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$project_dir/scripts/user-install-paths.sh"
data_home=$speaktext_data_home
bin_dir="$speaktext_user_home/.local/bin"
libexec_dir="$speaktext_user_home/.local/libexec/speaktext"
python_dir="$data_home/speaktext/python"
applications_dir="$data_home/applications"
icons_dir="$data_home/icons/hicolor/scalable/apps"
dbus_services_dir="$data_home/dbus-1/services"
extension_uuid="speaktext@local"
extension_dir="$data_home/gnome-shell/extensions/$extension_uuid"

if [ ! -x "$project_dir/build/speaktext-worker" ]; then
    printf 'Native worker is missing; run scripts/bootstrap.sh first.\n' >&2
    exit 1
fi

if [ "${SPEAKTEXT_SKIP_EXTENSION_ENABLE:-0}" != "1" ] && \
        command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions disable "$extension_uuid" >/dev/null 2>&1 || true
fi

install -d \
    "$bin_dir" \
    "$libexec_dir" \
    "$python_dir" \
    "$applications_dir" \
    "$icons_dir" \
    "$dbus_services_dir" \
    "$extension_dir"
install -m 0755 "$project_dir/scripts/speaktext-launcher" "$bin_dir/speaktext"
install -m 0755 "$project_dir/build/speaktext-worker" "$libexec_dir/speaktext-worker"
install -d "$python_dir/speaktext"
install -m 0644 "$project_dir"/src/speaktext/*.py "$python_dir/speaktext/"
install -m 0644 "$project_dir/data/local.SpeakText.svg" "$icons_dir/local.SpeakText.svg"
sed "s|@EXEC@|$bin_dir/speaktext|" "$project_dir/data/local.SpeakText.desktop.in" \
    > "$applications_dir/local.SpeakText.desktop"
chmod 0644 "$applications_dir/local.SpeakText.desktop"
sed "s|@EXEC@|$bin_dir/speaktext|" "$project_dir/data/local.SpeakText.service.in" \
    > "$dbus_services_dir/local.SpeakText.service"
chmod 0644 "$dbus_services_dir/local.SpeakText.service"
install -m 0644 "$project_dir/extension/extension.js" "$extension_dir/extension.js"
install -m 0644 "$project_dir/extension/metadata.json" "$extension_dir/metadata.json"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
fi

extension_status="installed but not enabled"
if [ "${SPEAKTEXT_SKIP_EXTENSION_ENABLE:-0}" = "1" ]; then
    extension_status="extension enable skipped"
elif command -v gnome-extensions >/dev/null 2>&1 && \
        gnome-extensions enable "$extension_uuid" >/dev/null 2>&1; then
    extension_status="top-bar extension enabled"
else
    printf '%s\n' \
        "GNOME has not loaded the new extension yet. Log out and back in, then run:" \
        "  gnome-extensions enable $extension_uuid" >&2
fi

printf 'Installed SpeakText for the current user (%s). Run: %s/speaktext\n' \
    "$extension_status" "$bin_dir"
