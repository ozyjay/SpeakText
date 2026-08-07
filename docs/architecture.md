# Architecture

## Runtime overview

SpeakText is a GTK/libadwaita application with a persistent native
`whisper.cpp` worker and a small GNOME Shell status extension. Dictation and
portal integration remain in Python; model inference remains in the C++ worker.

```text
GNOME top-bar extension ◄── content-free D-Bus status/control ──► GTK app
                                                               │
Global Shortcuts portal
        │ Activated / Deactivated
        ▼
DictationCoordinator ──► AudioCapture ──► pw-record ──► PipeWire microphone
        │                       │
        │                       └── raw 16 kHz mono s16 PCM in memory
        ▼
TranscriptionWorker ── framed pipes ──► speaktext-worker ──► Whisper model
        │
        ▼
TextInjector ──► Remote Desktop keyboard portal ──► current Wayland cursor
        │
        └── failure before insertion ──► Wayland clipboard + notification
```

The Shell extension receives the state, a content-free status message, and a
boolean indicating whether recovery text is available. It never receives PCM
or transcript text and cannot start dictation or access the microphone,
portals, worker, or clipboard. It can request cancellation, but the Python
application forwards that request to the coordinator, which remains the sole
owner of the state transition.

## Application state

`DictationCoordinator` exclusively owns this sequence:

```text
Starting → Ready → Recording → Transcribing → Inserting → Ready
                   │              │              │
                   └──────────────┴──────────────┴──► Error → Ready
                   │
                   └── cancel → Ready
```

- Activation is accepted only in `Ready`.
- Repeated activation while busy is ignored.
- Releasing the shortcut stops recording; a two-minute timer provides a hard
  stop if release is never reported.
- Cancelling stops microphone capture, discards its in-memory PCM, and returns
  directly to `Ready` without transcription or insertion.
- Recordings shorter than 300 ms and empty PCM buffers are discarded.
- Runtime errors are reported and return to `Ready`; model-startup failures stay
  visible until setup is retried.

## Audio and transcription protocol

`AudioCapture` starts `pw-record` with raw 16 kHz, mono, signed-16 output and
reads stdout directly into memory. It sends `SIGINT` to close capture cleanly and
kills the process only when shutdown times out.

The native worker loads `ggml-base.en.bin` once, prints `READY\n`, then processes
one request at a time:

1. Python writes a four-byte little-endian PCM byte count.
2. A zero count requests graceful shutdown.
3. Otherwise, Python writes exactly that many signed-16 PCM bytes.
4. The worker returns a four-byte little-endian UTF-8 byte count followed by the
   transcript.
5. A zero-length response means that no speech was recognised.

The coordinator enforces a 120-second recording limit. The worker accepts up to
125 seconds to tolerate PipeWire's shutdown tail.

## Portal sessions

SpeakText opens a dedicated, unsandboxed D-Bus connection for portal traffic
and registers `local.SpeakText` with the host portal registry before making any
portal request. Global Shortcuts and Remote Desktop share that registered
connection. Keeping it separate from GTK's shared bus connection ensures no
toolkit portal request can race ahead of registration. Older portal versions
without the registry fall back to their automatic application identification.

`GlobalShortcutPortal` creates a session and requests shortcut ID `dictate`
with preferred trigger `CTRL+ALT+space`. GNOME owns the final binding and emits
activation and deactivation signals. Toggle mode is available when a
compositor does not emit release reliably.

After `TextInjector` has preflighted the complete transcript,
`KeyboardPortal` opens a Remote Desktop session and requests device type
`1`—keyboard only—with persistence mode `2`. Each successful restoration
returns a new single-use token, which replaces the previous token in the
private settings file. The session closes immediately after insertion or an
insertion failure. No Remote Desktop session is held while SpeakText is idle,
and no screen, pointer, or touchscreen source is selected.

## Insertion and recovery

`TextInjector` converts the complete transcript to XKB keysyms before sending
anything, then acquires keyboard access for that insertion only. Newlines map
to `Return` and tabs map to `Tab`.

- If permission is unavailable or preflight fails, the complete transcript is
  copied to the clipboard.
- If the first portal call fails, clipboard fallback is still safe.
- If any keyboard event has already been sent, the result is marked partial and
  is not retried. The full transcript remains in memory for explicit copying.
- The keyboard portal session closes after every insertion attempt, including
  permission and key-event failures.
- Successful insertion clears the in-memory recovery transcript.

Wayland deliberately prevents SpeakText from discovering or restoring the
original application focus. Insertion therefore targets the cursor focused when
transcription completes.

## Stored paths

- Model: `$XDG_DATA_HOME/speaktext/models/ggml-base.en.bin`
- Settings: `$XDG_CONFIG_HOME/speaktext/config.json`, mode `0600`
- Diagnostics: `$XDG_STATE_HOME/speaktext/speaktext.log`
- User-local worker: `~/.local/libexec/speaktext/speaktext-worker`
- GNOME extension:
  `$XDG_DATA_HOME/gnome-shell/extensions/speaktext@local`
- D-Bus activation file:
  `$XDG_DATA_HOME/dbus-1/services/local.SpeakText.service`

Each XDG variable falls back to its conventional directory beneath the user's
home.
