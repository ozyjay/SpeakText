#!/usr/bin/env bash

speaktext_user_home=$HOME
speaktext_data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
speaktext_snap_data_home=0

if [ -n "${SNAP_USER_DATA:-}" ] && \
        [ "$speaktext_data_home" = "$SNAP_USER_DATA/.local/share" ]; then
    speaktext_snap_data_home=1
elif [ -n "${SNAP_USER_COMMON:-}" ] && \
        [ "$speaktext_data_home" = "$SNAP_USER_COMMON/.local/share" ]; then
    speaktext_snap_data_home=1
fi

if [ "$speaktext_snap_data_home" = "1" ]; then
    speaktext_user_home=${SNAP_REAL_HOME:-$HOME}
    speaktext_data_home="$speaktext_user_home/.local/share"
    printf '%s\n' \
        "Ignoring Snap-private XDG_DATA_HOME; using $speaktext_data_home." >&2
fi
