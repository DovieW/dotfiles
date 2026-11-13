# Preferred audio devices

`config/wireplumber/60-preferred-audio.conf` stores WirePlumber 0.5+ ALSA
node priorities, installed by the KDE profiles (including kubuntu-desktop):

1. Lenovo Speakerphone 6000: microphone and speaker.
2. Burr-Brown / TI PCM2902 USB Audio CODEC: dynamic microphone input and audio output.
3. Other available devices, using their normal priorities.

The rules match model names, without USB port numbers or individual serials.
With automatic selection enabled, connecting the speakerphone makes it the
default; removing it selects the USB Audio CODEC if available. On computers
without these devices the rules have no effect. Volumes and mute states are
not changed. Sink priorities stay below 1500 to avoid their monitor sources
outranking real microphones.

Apply only this configuration:

```sh
bin/dot apply --profile kubuntu-desktop --tags audio --check
bin/dot apply --profile kubuntu-desktop --tags audio
```

The apply command does not interrupt audio sessions. At a convenient time,
log out and back in, or run `systemctl --user restart wireplumber` (which can
briefly interrupt audio). To opt into priorities, clear previously saved manual
selections once with `wpctl clear-default`. This forgets the input and output
selection history, not volume or mute settings. A later manual device selection
in KDE or `wpctl set-default` takes precedence; `wpctl clear-default` returns
to automatic selection. Reapplying dotfiles does not reset manual selections.

Check the active choice with `wpctl status`, `pactl get-default-source`, and
`pactl get-default-sink`. Applications pinned to a specific microphone or speaker
may need their own device selector changed to “Default”. Applications already
running may need to reopen their audio stream.

The configuration follows WirePlumber's [node priority policy](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/priorities.html).
