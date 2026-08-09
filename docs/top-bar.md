# GNOME top-bar integration

SpeakText uses a small GNOME Shell 50 extension because GTK applications cannot
add controls directly to the Shell panel on Wayland. The extension is a status
and control surface only; the Python application remains the sole owner of
dictation, IBus, the clipboard, and the transcription worker.

## What the indicator shows

The symbolic icon follows the application state:

| State | Meaning |
| --- | --- |
| Starting | The app identifies whether it is checking, downloading, or loading the local model |
| Ready | Double-tapping the configured key can begin dictation in an active context |
| Recording | Microphone capture is active |
| Transcribing | Local Whisper inference is active |
| Inserting | The transcript is being committed through IBus |
| Error | Setup or dictation needs attention |
| Disconnected | The application is not running |

Its menu can open or start SpeakText, cancel an active recording, copy an
explicitly retained recovery transcript, and quit the application. Cancelling
and copying are performed inside the Python process; neither PCM nor text is
returned to the extension.

Routine recording, transcription, insertion, and successful-completion states
are shown only through the top-bar icon and its status text. Desktop
notifications are reserved for errors and clipboard fallback that needs user
attention.

SpeakText does not open a Remote Desktop session, so dictation does not produce
GNOME's orange remote-access indicator.

## D-Bus contract

The application owns `local.SpeakText` on the session bus and exports
`local.SpeakText.Control` at `/local/SpeakText`:

- `GetStatus() → (state, message, can_copy)`
- `ActivateWindow()`
- `CopyLastTranscript() → copied`
- `CancelRecording()`
- `Quit()`
- `StatusChanged(state, message, can_copy)`

Status messages must remain content-free. The interface must never grow a
transcript, PCM, clipboard-content, microphone, IBus, or dictation-triggering
method. The installed D-Bus service activates SpeakText without opening its
window so the indicator can keep it available after login.

## Installation lifecycle

`make install-user` installs `speaktext@local` below the user XDG data directory
and attempts to enable it. GNOME may require one logout and login before it
discovers a newly installed extension. Check or enable it with:

```powershell
gnome-extensions info speaktext@local
gnome-extensions enable speaktext@local
```

`make uninstall-user` disables and removes the extension and the D-Bus
activation file. The existing model and diagnostics remain
available unless removed separately.
