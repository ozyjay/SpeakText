# Privacy and security

SpeakText is designed for local dictation without transcript history or cloud
processing.

## Data handling

| Data | Location | Lifetime |
| --- | --- | --- |
| Microphone PCM | Python process memory and worker pipe | Current recording and transcription |
| Transcript | Process memory and active IBus context | Cleared after successful insertion |
| Test transcript | Process memory and application window | Until cleared, replaced, the window closes, or the app exits |
| Failed transcript | Process memory and optionally clipboard | Until copied, replaced, or the app exits |
| Whisper model | XDG data directory | Until manually removed |
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

SpeakText uses the local IBus input framework. Its selected engine receives key
events for the active text context, recognises only releases of the configured
Shift or Control key for the dictation gesture, and passes every key event
through unchanged. IBus also
receives the completed transcript for that active context.

If the SpeakText input method is not active, SpeakText degrades to clipboard
recovery. It does not request Remote Desktop, screen, pointer, touchscreen, or
synthetic keyboard access or global keyboard hooks.
Losing the active IBus context while recording cancels capture and discards its
in-memory PCM.

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

Protected fields may decline input-method commits. SpeakText never inspects the
surrounding text or reads content from the focused application.

## Reporting problems

Before sharing diagnostics, review them for paths or environmental information.
Do not attach microphone recordings, clipboard captures, configuration files,
model files, or dictated text unless deliberately required and safely redacted.
