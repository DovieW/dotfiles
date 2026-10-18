# OBS recording

Kubuntu laptop and desktop profiles install the distribution OBS Studio package.
The `config,obs` Ansible tasks seed an editable **Dotfiles Native 60fps** profile.
The active KDE display mode is detected in physical pixels, independent of desktop scaling.
Run the seed tasks from a KDE session. Select it from OBS's Profile menu. Subsequent applies preserve GUI adjustments
and do not change the active profile, scenes, microphone, or capture permissions.

Defaults: native primary display resolution for canvas/output, 60 fps, H.264 x264 veryfast CRF 20,
MKV, AAC 320 kbps stereo at 48 kHz, saved under `~/Videos/OBS`.
CRF provides variable bitrate compression; lower values increase quality and size.
These settings follow https://obsproject.com/kb/advanced-recording-settings-guide.
Software encoding is portable across machines. If CPU load causes encoding lag,
select a supported hardware encoder in Settings → Output → Recording and use
OBS's recommended constant-quality settings. Validate with a representative clip
and View → Stats before a long recording; a profile alone cannot guarantee 60 fps.

On Wayland add Screen Capture (PipeWire) and choose the display/window in the
portal. Add the intended microphone and desktop audio, listen to a short test,
and keep voice peaks around -12 to -6 dB without hitting red. Use headphones to
avoid echo. Add RNNoise suppression for a noisy mic and a limiter at -1 dB if
needed; filters and input gain depend on the microphone and room and are not
forced globally. All sources must route to track 1 for this single-mix preset.
OBS File → Remux Recordings can convert MKV to MP4 without re-encoding.
