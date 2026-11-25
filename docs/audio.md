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

Apply the USB audio priorities and automatic volume reset:

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

## Volume popup device icon

The Plasma volume popup uses the active output and its current port. Bluetooth
stereo earbuds and wired headphones use the headphones icon. Bluetooth call
audio uses the headset icon. Speakers and line out use the speaker icon, and
HDMI or DisplayPort uses a display icon. USB audio interfaces and digital outputs
with no more specific match use a sound-card icon. Mute and high-volume warnings
use Plasma's standard icons.

The bar animates between output volume levels while the percentage displays the
actual level. The animation also applies to hardware volume keys.

Apply with `bin/dot apply --profile kubuntu-laptop --tags audio-osd`, then
log out and back in or restart the `plasma-plasmashell.service` user unit.

## Automatic volume reset

On the Kubuntu desktop and laptop profiles, `dot-audio-mute.service` listens for
Plasma Wayland display power events. When all displays turn off, including at
the lock screen, it starts a 30-minute timer. It cancels the timer when a
display comes back on. If the timer expires, it sets the default audio output
to 0%.

The service also sets the default output to 0% just before sleep and again on
wake. The mute switch and microphones are untouched. Raise the volume when
you want sound again.

Apply just the watcher with `bin/dot apply --profile kubuntu-desktop --tags audio-mute`
or use `kubuntu-laptop` on the laptop. Check its activity with
`journalctl --user -u dot-audio-mute.service`.
