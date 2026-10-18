# OBS recording

Kubuntu laptop and desktop profiles install the distribution OBS Studio package.
The `config,obs` Ansible tasks seed an editable **Dotfiles Native 60fps** profile.
The active KDE display mode is detected in physical pixels, independent of desktop scaling.
Run the seed tasks from a KDE session. Select it from OBS's Profile menu. Subsequent applies preserve GUI adjustments
and do not change the active profile, scenes, microphone, or capture permissions.

Defaults: native primary display resolution for canvas/output, 60 fps, H.264 x264 veryfast CRF 20,
Hybrid MP4, AAC 320 kbps stereo at 48 kHz, saved under `~/Videos/OBS`.
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
Hybrid MP4 remains recoverable if recording is interrupted and finalizes as a regular
MP4 when stopped normally. The final buffered portion can still be lost on a crash.

## Voice and presenter audio preset

The reviewed preset is tracked in `config/obs/audio-preset.json`. With OBS closed,
apply it to an existing collection containing exactly one PulseAudio microphone
source and one PulseAudio output source:

```sh
scripts/obs-audio-profile ~/.config/obs-studio/basic/scenes/Untitled.json --check
scripts/obs-audio-profile ~/.config/obs-studio/basic/scenes/Untitled.json
```

The tool backs up the scene, refuses to modify a running OBS instance, and refuses
ambiguous sources or custom filters. It removes duplicate default global captures,
preserves the explicitly selected devices and screen source, disables monitoring
to prevent feedback, and assigns mic to tracks 1+2 and desktop to tracks 1+3.
The native recording profile records all three AAC tracks at 320 kbps: track 1 is
the normal playback mix; tracks 2 and 3 allow independent adjustment in an editor.
Do not route extra audio sources into the mix without reviewing headroom.

Mic chain: RNNoise → +12 dB gain → 3:1 compressor at -18 dB, 6 ms attack,
150 ms release, +6 dB makeup → -7 dB limiter, 60 ms release. No noise gate
is applied, to avoid cutting soft speech. Desktop/presenter chain: 3:1 compressor
at -20 dB, 6 ms attack, 150 ms release, +6 dB makeup → -7 dB limiter.
The two -7 dB ceilings leave approximately 1 dB of headroom when summed.
A limiter cannot repair audio clipped at the microphone or inside the presenter app.

The mic gain was chosen for a Hollyland sample with peaks near -19 dBFS, with
another sample reaching -14.4 dBFS. It is a starting point, not automatic loudness
normalization. Other microphones, placement, and presenter levels need a short
test recording. 800% linear amplitude is about +18 dB; use the named gain and
compressor controls instead of raising system input volume globally. Leave the
OBS faders at 0 dB so the limiter headroom remains effective. Keep headphones on.

## Compact laptop meeting profile

**Dotfiles Laptop Meeting** records directly with the settings used for the
smaller meeting copy: 1280×800 output at 30 fps, H.264 x264 medium CRF 23,
one 160 kbps AAC stereo track at 48 kHz, and Hybrid MP4 in `~/Videos/OBS`.
The canvas stays at the detected native display size so existing screen source
placement remains valid. The 16:10 output matches the laptop panel; use another
output aspect ratio for a different-shaped capture. This profile is separate
from Native 60fps and uses the same selected scene collection and audio filters.
Select it in OBS's Profile menu before recording. Both voice and presenter
sources must be assigned to track 1; the reviewed audio preset already does this.

Ansible seeds both profiles without replacing later GUI changes. To seed just
the compact profile from a KDE session:

```sh
bin/dot apply --profile kubuntu-laptop --tags obs-small
```

This records a small file directly; it does not schedule post-recording
compression or delete originals. Native 60fps remains available for recording
at full quality and compressing afterward. File size depends on video content.
