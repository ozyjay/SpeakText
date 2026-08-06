# GNOME top-bar integration

SpeakText uses a small GNOME Shell 50 extension because GTK applications cannot
add controls directly to the Shell panel on Wayland. The extension is a status
and control surface only; the Python application remains the sole owner of
dictation, portals, the clipboard, and the transcription worker.

## What the indicator shows

The symbolic icon follows the application state:

| State | Meaning |
| --- | --- |
| Starting | The model and desktop services are being prepared |
| Ready | The shortcut can begin dictation |
| Recording | Microphone capture is active |
| Transcribing | Local Whisper inference is active |
| Inserting | Keysyms are being sent through the keyboard portal |
| Error | Setup or dictation needs attention |
| Disconnected | The application is not running |

Its menu can open or start SpeakText, copy an explicitly retained recovery
transcript, and quit the application. Copying is performed inside the Python
process; the text is not returned to the extension.

## D-Bus contract

The application owns `local.SpeakText` on the session bus and exports
`local.SpeakText.Control` at `/local/SpeakText`:

- `GetStatus() → (state, message, can_copy)`
- `ActivateWindow()`
- `CopyLastTranscript() → copied`
- `Quit()`
- `StatusChanged(state, message, can_copy)`

Status messages must remain content-free. The interface must never grow a
transcript, PCM, clipboard-content, microphone, portal, or dictation-triggering
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
activation file. The existing model, private settings, and diagnostics remain
available unless removed separately.
