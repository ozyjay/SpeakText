# SpeakText

SpeakText is private, local speech-to-text dictation for Fedora 44 Workstation
on GNOME Wayland. Hold the configured global shortcut, speak, then release it;
SpeakText transcribes with a local Whisper model and inserts the result at the
currently focused cursor.

No audio or transcript is written to disk, sent over the network, included in
diagnostic logs, or retained after successful insertion. The only runtime
network request is the first model download.

## Platform and behaviour

- Fedora 44 Workstation, GNOME 50, and Wayland only.
- English dictation up to two minutes using `ggml-base.en.bin`.
- `CTRL+ALT+space` is requested as the default push-to-talk shortcut. GNOME's
  portal dialog owns the final binding.
- A settings switch provides press-once/start, press-again/stop fallback if a
  compositor fails to report shortcut release.
- Keyboard input uses the XDG Remote Desktop portal with keyboard-only access;
  no screen or pointer access is requested.
- If keyboard access is unavailable, SpeakText copies the transcript and shows
  a notification. A partial insertion is never retried automatically.
- Wayland does not expose the original focused application. Text goes to the
  cursor focused when transcription finishes.

## Build

The current Fedora 44 Workstation image normally contains most dependencies.
Check without changing the system:

```bash
./scripts/bootstrap.sh --check
```

If anything is missing, the script prints a suggested `dnf` command but never
runs `sudo`. Once dependencies are available, build the CPU-only native worker:

```bash
./scripts/bootstrap.sh
```

This fetches the pinned `whisper.cpp` 1.9.1 source during the first build. Run
the development copy with:

```bash
make run
```

The first run downloads and verifies the approximately 142 MiB English model.
GNOME then asks you to approve the global shortcut and keyboard-only remote
control. Denying keyboard control leaves clipboard fallback available.

## User-local installation

Install beneath `~/.local` without root access:

```bash
make install-user
```

Launch **SpeakText** from the GNOME application grid, or run
`~/.local/bin/speaktext`. Closing the window keeps dictation running; use the
window's **Quit** button to end it.

To remove executables and desktop metadata while retaining the downloaded
model and settings:

```bash
make uninstall-user
```

Retained data can be removed manually from:

- `${XDG_DATA_HOME:-~/.local/share}/speaktext`
- `${XDG_CONFIG_HOME:-~/.config}/speaktext`
- `${XDG_STATE_HOME:-~/.local/state}/speaktext`

## Testing

Run the dependency-free Python suite:

```bash
make test
```

The tests use fake audio, portal, clipboard, and worker implementations, so
they do not request desktop permissions or access the microphone. After the
native worker and model are available, run the manual acceptance checklist in
[`docs/acceptance-testing.md`](docs/acceptance-testing.md).

## Architecture

- `AudioCapture` streams raw 16 kHz mono signed-16 PCM from `pw-record` into
  memory.
- `TranscriptionWorker` owns a persistent C++ process with the model loaded
  once and communicates through a length-prefixed pipe protocol.
- `GlobalShortcutPortal` and `KeyboardPortal` isolate XDG portal sessions.
- `TextInjector` preflights the entire transcript through `libxkbcommon` before
  sending keysyms.
- `DictationCoordinator` exclusively owns the application state machine.

Diagnostic logs are stored under `$XDG_STATE_HOME/speaktext` and contain state,
timing, and error metadata only.
