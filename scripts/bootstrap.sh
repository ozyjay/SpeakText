#!/usr/bin/env bash
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
missing=""

check_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        missing="${missing} $2"
    fi
}

check_command python3 python3
check_command pw-record pipewire-utils
check_command cmake cmake
check_command ninja ninja-build
check_command g++ gcc-c++
check_command git git

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')" >/dev/null 2>&1; then
    missing="${missing} python3-gobject gtk4 libadwaita"
fi

if ! ldconfig -p 2>/dev/null | grep -q 'libxkbcommon\.so'; then
    missing="${missing} libxkbcommon"
fi

if [ -n "$missing" ]; then
    printf 'Missing Fedora packages:%s\n' "$missing" >&2
    printf 'Install them explicitly, then run this script again.\n' >&2
    printf 'Suggested command: sudo dnf install%s\n' "$missing" >&2
    exit 1
fi

if [ "${1:-}" = "--check" ]; then
    printf 'All required Fedora dependencies are available.\n'
    exit 0
fi

cmake -S "$project_dir" -B "$project_dir/build" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$project_dir/build" --target speaktext-worker
printf 'Built %s/build/speaktext-worker\n' "$project_dir"

