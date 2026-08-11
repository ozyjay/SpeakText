# Fedora 44 acceptance testing

Run these checks in a GNOME Wayland session after building SpeakText. Portal
tests deliberately require visible user approval and should not be automated
in an unattended session.

1. Install with `make install-user`, then log out and back in so IBus loads the
   user-local SpeakText component. Confirm a microphone icon appears in the
   GNOME top bar and its menu can open the settings window.
2. Start SpeakText from the top-bar menu; confirm startup identifies whether it
   is checking the local model, downloading it with byte progress, or loading
   speech recognition. The checking and loading stages show an active progress
   bar; the first model load can take up to 90 seconds. Confirm `ibus engine`
   reports `speaktext` without running `ibus engine speaktext` manually.
3. Confirm the installer retained the existing keyboard layouts and added
   **SpeakText** to GNOME's input-source menu. Confirm it was selected when the
   application started and that no Global Shortcuts or Remote Desktop prompt
   and no orange remote-access indicator appears. Do not expect this
   runtime-registered engine in `ibus list-engine`.
4. Confirm the top-bar icon and status text follow Ready, Recording,
   Transcribing, Reviewing, Inserting, and Error states without routine desktop
   notifications.
5. In the SpeakText window, choose **Start test**, speak a short sample, then
   choose **Stop test**. Confirm the recognised text appears only under **Test
   result**, no text is inserted elsewhere, and **Clear test result** removes
   it. Close and reopen the window to confirm any displayed test text is
   cleared.
6. In GNOME Text Editor, Firefox, native-Wayland VS Code, and Ptyxis, place the
   cursor in an editable area, rapidly tap either Shift key twice and speak for
   five to ten seconds. Confirm provisional text appears at the cursor and may
   revise as speech continues. Double-tap Shift to stop, confirm the final text
   remains a preview, then double-tap Shift again to commit it. Use a
   Fedora-installed native-Wayland VS Code build and confirm its main process
   does not contain `--ozone-platform=x11`.
7. In the SpeakText window, change the gesture key to Control. Repeat dictation
   with double-Control, confirm Shift no longer activates it, then restart
   SpeakText and confirm the Control choice was retained.
8. Start a recording, choose **Cancel recording** from the top-bar menu, and
   confirm immediate return to Ready with no transcription, insertion, or
   clipboard change. Repeat with the button in the SpeakText window, then start
   another recording and tap Control once. Confirm cancellation occurs only
   after the short double-tap window expires. Stop another recording and confirm
   **Discard preview** clears its uncommitted text without changing the target.
9. Dictate punctuation, a newline, and Unicode words such as “café”; confirm the
   committed text is correct.
10. Change focus while recording; confirm the recording is cancelled. Stop a
   new recording, then change focus while reviewing; confirm the uncommitted
   preview is discarded and is never committed in the newly focused context.
11. Switch away from the SpeakText input source, double-tap Control, and confirm
   recording does not start. Finish a recording in an editable context, then
   deactivate the SpeakText input source while transcription or review is in
   progress; confirm the uncommitted preview is discarded. Confirm **Copy last
   transcript** works from the top-bar menu without displaying it after a
   deliberately failed confirmed commit.
12. Disconnect or mute the microphone, dictate silence, rapidly repeat the
   gesture, and quit during recording and transcription. Confirm recovery with
   no crash or stale recording.
13. Leave a recording active for two minutes; confirm automatic stop, final
    preview, and that a separate confirmation is required to commit it.
14. Restart the machine, start SpeakText, and dictate again; confirm the engine
    is selected automatically and IBus insertion remains available without a
    Remote Desktop prompt.
15. Search `$XDG_CONFIG_HOME`, `$XDG_STATE_HOME`, and `/tmp` for distinctive
    dictated words. Confirm that neither transcripts nor PCM data were written.

For a warm model on the target CPU, recording should begin within 300 ms and a
ten-second sample should be inserted within five seconds of release.
