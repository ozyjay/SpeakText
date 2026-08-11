# Architecture

## Runtime overview

SpeakText is a GTK/libadwaita application with a persistent native
`whisper.cpp` worker and a small GNOME Shell status extension. Dictation and
IBus integration remains in Python; model inference remains in the C++ worker.

```text
GNOME top-bar extension ◄── content-free D-Bus status/control ──► GTK app
                                                               │
Active SpeakText IBus context
        │ configured double-tap / single-tap modifier gesture
        ▼
DictationCoordinator ──► AudioCapture ──► pw-record ──► PipeWire microphone
        │                       │
        │                       └── raw 16 kHz mono s16 PCM in memory
        ▼
TranscriptionWorker ── framed pipes ──► speaktext-worker ──► Whisper model
        │
        ▼
IBusTextInjector ──► active IBus text context ──► current Wayland cursor
        │
        └── inactive input method ──► Wayland clipboard + notification
```

The Shell extension receives the state, a content-free status message, and a
boolean indicating whether recovery text is available. It never receives PCM
or transcript text and cannot start dictation or access the microphone,
IBus, worker, or clipboard. It can request cancellation, but the Python
application forwards that request to the coordinator, which remains the sole
owner of the state transition.

## Application state

`DictationCoordinator` exclusively owns this sequence:

```text
Starting → Ready → Recording → Transcribing → Reviewing → Inserting → Ready
                   │              │                 │             │
                   └──────────────┴─────────────────┴─────────────┴──► Error → Ready
                   │                                │
                   └────────────── cancel ──────────┴──► Ready
```

- Activation is accepted only in `Ready`.
- Repeated activation while busy is ignored.
- A second rapid double-tap stops recording; a two-minute timer provides a hard
  stop if no finishing gesture is received. A third double-tap commits the
  completed preview.
- Cancelling stops microphone capture or discards a review preview, then returns
  directly to `Ready` without committing text.
- The in-window microphone test follows the same capture and transcription
  path, but returns the recognised text only to the GTK window and never calls
  the IBus injector.
- Recordings shorter than 300 ms and empty PCM buffers are discarded.
- Runtime errors are reported and return to `Ready`; model-startup failures stay
  visible until setup is retried.

## Audio and transcription protocol

`AudioCapture` starts `pw-record` with raw 16 kHz, mono, signed-16 output and
reads stdout directly into memory. While recording, the coordinator sends a
complete in-memory snapshot to the existing worker approximately every 2.5
seconds and displays each recognised result as a provisional IBus pre-edit.
The most recent words can change as more audio arrives. It sends `SIGINT` to
close capture cleanly and kills the process only when shutdown times out.

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

## IBus input context

SpeakText dynamically registers an IBus engine for the lifetime of the
application and selects it after registration. The user installer adds
**SpeakText** as a GNOME input source without removing existing keyboard
layouts. The engine passes ordinary key events through unchanged.

On release of the configured Shift or Control key, the engine recognises a
350 ms double-tap window. A double-tap starts or finishes recording, and a
double-tap while reviewing commits the preview. While recording or reviewing,
a single tap cancels after that window expires. The choice is stored under
`$XDG_CONFIG_HOME/speaktext`. Because IBus sends these events only to the
selected engine with an active input context, the gesture cannot start
microphone capture when SpeakText has nowhere to insert text. Losing that
context while recording cancels and discards the recording immediately; losing
it while reviewing clears and discards the uncommitted pre-edit.

`IBusTextService` renders each provisional transcript with IBus pre-edit APIs;
that text is visible at the active cursor but is not committed to the target
application. When the user confirms the final preview while that context
remains active, `IBusTextInjector` commits the complete UTF-8 transcript. No
Global Shortcuts or Remote Desktop portal session and no synthetic keyboard
event is used.

## Insertion and recovery

`IBusTextInjector` commits a confirmed complete preview as one text operation.

- If the SpeakText input method is not active in an editable context, the
  complete transcript is copied to the clipboard.
- Successful insertion clears the in-memory recovery transcript.

Wayland deliberately prevents SpeakText from discovering or restoring the
original application focus. The provisional pre-edit belongs to its current
IBus context, so an uncommitted preview is discarded if that context is lost.

## Stored paths

- Model: `$XDG_DATA_HOME/speaktext/models/ggml-base.en.bin`
- Gesture settings: `$XDG_CONFIG_HOME/speaktext/settings.ini`
- Diagnostics: `$XDG_STATE_HOME/speaktext/speaktext.log`
- User-local worker: `~/.local/libexec/speaktext/speaktext-worker`
- GNOME extension:
  `$XDG_DATA_HOME/gnome-shell/extensions/speaktext@local`
- D-Bus activation file:
  `$XDG_DATA_HOME/dbus-1/services/local.SpeakText.service`

Each XDG variable falls back to its conventional directory beneath the user's
home.
