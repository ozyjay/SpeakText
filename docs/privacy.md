# Privacy and security

SpeakText is designed for local dictation without transcript history or cloud
processing.

## Data handling

| Data | Location | Lifetime |
| --- | --- | --- |
| Microphone PCM | Python process memory and worker pipe | Current recording and transcription |
| Transcript | Process memory and keyboard portal | Cleared after successful insertion |
| Failed transcript | Process memory and optionally clipboard | Until copied, replaced, or the app exits |
| Whisper model | XDG data directory | Until manually removed |
| Portal restore token | Mode-`0600` XDG configuration file | Replaced after successful restoration; cleared after an acquisition failure |
| Diagnostics | XDG state directory | Rotating local files |
| Top-bar status | Session D-Bus and GNOME Shell memory | Application session |

Audio and transcripts must never be written to temporary files. Logs may record
state transitions, timings, byte counts, paths, and error categories, but not
audio bytes, recognised words, clipboard contents, or typed text.

## Network access

Runtime transcription is offline. Network access is used only to:

- fetch the pinned `whisper.cpp` source during the initial native build; and
- download the official `ggml-base.en.bin` model on first application launch.

The model is accepted only when its SHA-256 digest matches the value pinned in
`src/speaktext/constants.py`. No accounts, API keys, telemetry, analytics, or
cloud speech services are used.

## Desktop permissions

SpeakText uses two XDG portal sessions:

- Global Shortcuts receives only the configured activation and deactivation
  events. It is not a general keyboard listener.
- Remote Desktop opens only after a transcript passes insertion preflight,
  requests keyboard device type `1`, and closes after that insertion attempt.
  SpeakText does not select screen-cast sources and does not request pointer or
  touchscreen access.

GNOME presents and owns permission decisions. If keyboard permission is denied
or revoked, SpeakText degrades to clipboard recovery rather than bypassing the
desktop security model. GNOME Shell may keep its generic orange remote-access
indicator visible briefly after the session closes; this does not mean that
SpeakText kept the session open.

## Top-bar interface

The GNOME Shell extension uses the session bus only for lifecycle controls and
content-free status. The interface exposes the state name, a short status or
error message, and whether **Copy last transcript** is available. The copy
operation runs inside the application; neither the D-Bus reply nor the Shell
extension contains the transcript. Microphone PCM and recognised text are
never sent to GNOME Shell.

## Wayland limitations

SpeakText cannot inspect which application or control owns focus. The transcript
is inserted wherever the cursor is focused when recognition completes. Users
should avoid changing focus to sensitive fields while transcription is running.

Portal keyboard events may be rejected by protected surfaces. Partial insertion
is reported without an automatic retry because replaying the complete transcript
could duplicate already inserted text.

## Reporting problems

Before sharing diagnostics, review them for paths or environmental information.
Do not attach microphone recordings, clipboard captures, configuration files
containing restore tokens, model files, or dictated text unless deliberately
required and safely redacted.
