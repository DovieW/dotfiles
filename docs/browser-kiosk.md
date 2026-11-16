# Family Photos browser kiosk

Status on 2026-11-15: installed and enabled. The owner confirmed successful
family-account sign-in and reopening with the library still accessible after
the authenticated exit restored restricted mode. The administrator exit
shortcut has also been physically tested. The installed runtime and Sway
configuration match the repository; the 12 targeted automated tests pass.
A subsequent restricted-mode trial found search unresponsive and video
playback stuck loading, without an explicit blocked-page error. Both worked
when website blocking was lifted. The allowlist now includes Google media,
API, and background account-refresh services; a restricted-mode retest is
pending, including album viewing and hardware controls. See the acceptance checklist below for the
remaining physical checks; this is not a claim that every escape route or
Google Photos feature has been tested.

No automatic recovery timer is installed, at the owner's request. A monitoring
agent is useful during supervised testing, but is not a guaranteed recovery
mechanism and is not required for ordinary operation. SSH recovery was not
verified and was reported unavailable during the initial failed trial.

The managed kiosk uses a separate `photos-kiosk` Linux user, a minimal Sway
session, and mandatory Chrome policies scoped to that account. Its browser
profile persists locally. It contains no personal Chrome profile, desktop
panel, launcher, or terminal shortcut. Ctrl+Alt+Backspace requests administrator
authentication to end the session; cancelling keeps the session running.

Sway replaces Cage from the [original research](browser-kiosk-research.md)
because the exit shortcut needs a system authentication prompt. The private
configuration does not include the distribution's normal Sway desktop config.
Configured shortcuts provide authenticated exit, volume/mute, and display
brightness; none launches a terminal or desktop. Server keys
for virtual-terminal switching are disabled through the XKB configuration.

## Install

From the repository, run:

```sh
pkexec ./scripts/browser-kiosk install
```

The installer requests system authentication, installs Sway without upgrading
existing packages, and creates a password-locked account with a private home
and `nologin` shell. It installs root-owned session wrappers, policies, a
desktop launcher, and guest-specific polkit restrictions. It reloads OpenSSH
after validating the guest login prohibition. It does not restart SDDM or
switch your current session.

A pre-existing account or installation destination is rejected on first
installation. Custom SDDM session wrappers require review. Other users are
delegated to the original distro session wrappers without changing arguments.
For the kiosk user, selecting any Wayland desktop runs the kiosk; X11 session
selection is refused. Its login shell prevents ordinary console shells, and
OpenSSH explicitly denies the kiosk account.

Set a password for the kiosk's normal graphical login using an interactive
terminal, never by placing the password in a command or configuration file:

```sh
sudo passwd photos-kiosk
```

Keep this password with the owner. It is distinct from the administrator
password required to exit. No automatic login is configured. Use normal login
for wallet unlocking; do not weaken KWallet or copy personal browser cookies.

## Enroll the family Google account

Before entering the kiosk for the first time, authenticate this command:

```sh
pkexec /usr/local/libexec/browser-kiosk enroll
```

Enrollment mode temporarily removes website blocking so Google CAPTCHA and
sign-in redirects can function. Internal Chrome pages, file access, downloads,
printing, and developer tools remain restricted, with `chrome://policy` available
for owner inspection. This mode is only for the owner during account setup. It ends any existing kiosk session. Sign in through the
normal login screen as `photos-kiosk`, select **Family Photos kiosk**, and
interactively sign into the intended family Google account. Verify the exact
account; no identifier or password is stored in this repository.

Use Ctrl+Alt+Backspace and authenticate as an administrator to end enrollment.
Normal `stop` restores the restricted Photos/service allowlist before ending
the session. An
expired login in locked mode requires a new owner-controlled enrollment step.
Do not hand over a session while it remains in enrollment mode.

## Normal use

Open **Family Photos guest session** in the application launcher. It locks the
owner's current session, waits for the lock acknowledgement, then requests the
login screen. Sign in as the kiosk user with **Family Photos kiosk** selected.
The session also rejects startup when another graphical user's session reports
that it is unlocked.

Chrome runs using its own persistent profile and restarts after closure. Five
rapid failures leave the restricted compositor blank, with the authenticated
exit shortcut still configured. No fallback terminal is launched. The system
polkit agent must display correctly above Chrome before this is accepted for
handoff. The owner can recover from another authenticated session using:

```sh
pkexec /usr/local/libexec/browser-kiosk stop
```

Returning to the owner's desktop still requires unlocking the owner's session.
Power loss, compositor crashes, and suspend/resume require physical testing;
no claim is made that software can prevent someone forcing a reboot.

## Touchpad and hardware keys

The existing system-wide `/etc/libinput/local-overrides.quirks` applies to
Sway as well as Plasma; there is no second per-user copy. On this laptop it
contains the CIRQ jump-detector workaround and keyd keyboard integration fix.
The kiosk explicitly matches the managed touchpad settings: flat acceleration,
pointer speed 0.2, scroll factor 0.1, and disable-while-typing. Plasma's desktop
switching/overview gestures are not installed into the restricted compositor.

Volume keys use the kiosk's own PipeWire session, in 5% steps capped at 100%,
with a mute toggle. Brightness keys use logind's active-session API in 20%
steps, with a 5% minimum to keep the screen visible. They do not grant the
guest administrative privileges or start Plasma's desktop services.

## Policies and acceptance

The file `/etc/opt/chrome/policies/managed/dotfiles-kiosk.json` is owned by
root, readable by the kiosk group only, and not writable by that group. This
avoids applying its restrictions to the owner's Chrome. Verify both users in
real browsers after installation or updates; a new Chrome profile alone does
not isolate Linux platform policies.

Read-only structural diagnostics:

```sh
pkexec /usr/local/libexec/browser-kiosk check
```

These diagnostics inspect policy contents and ownership; they do not restart
applications or prove runtime enforcement. Before handoff:

- Verify the effective mandatory policies in kiosk Chrome and absence of those
  restrictions in the owner's browser, using disposable profiles for testing.
- Complete Google login, then confirm `check` reports `locked`. Test Photos
  images/video and confirm Gmail, Search, local files, internal browser pages,
  downloads, printing, uploads, developer tools, and account changes are blocked.
- Test Alt+Tab, Super, Alt+F2, Ctrl+Alt+T, function-key VT switching, touchpad
  gestures, new windows, and browser closure. Check that a normal desktop
  cannot be selected for the kiosk account.
- Verify administrator authentication, rejection of an incorrect password,
  cancellation, and owner-session password protection. Test with all displays.
- Exercise browser/compositor crashes, suspend/resume, reboot, and network loss.
  Confirm owner notifications, clipboard data, and background audio do not leak.

Normal viewing is intended to include the library, photos, albums, search,
and video playback. The allowlist covers every path on the exact HTTPS
`photos.google.com` host, plus Google media and supporting services: the
`googleusercontent.com`, `googlevideo.com`, `gstatic.com`, and `googleapis.com`
domain families; exact `apis.google.com`, `video.google.com`, and `ogs.google.com`
hosts; and specific account cookie-refresh paths. These service exceptions can
also permit direct navigation to content hosted there. General Google Search,
Gmail, Drive, account management, and unrelated sites remain outside the
allowlist. It does not limit individual albums or make the
account read-only. URL policies constrain page and embedded-frame navigation;
they are not a network firewall that denies every image, script, or API request
to other hosts. See Chromium's
[navigation enforcement](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/components/policy/content/policy_blocklist_navigation_throttle.cc)
and [URL filter syntax](https://www.chromium.org/administrators/url-blocklist-filter-format/).

Uploads, downloads, and printing are deliberately unavailable. Links to
Google Account settings, Help, Maps, and other sites can show a blocked page;
those destinations are outside this viewing session. If Google requires a new
sign-in or CAPTCHA, the owner must repeat enrollment. A successful test today
does not guarantee that a future Google Photos change will use the same
navigation paths. If a viewing feature breaks, identify the blocked
navigation and add only the necessary exception rather than allowing all of
Google's sites.

The default restrictions also disable browser account sync, extensions,
camera/microphone access, and website notifications. Account website sign-in
is distinct from browser sign-in. Policies constrain navigation, not every
background network request. The family Photos account retains its own editing,
deletion, and sharing capabilities; this is not a read-only Photos account.

## Disable and reproduce

```sh
pkexec /usr/local/libexec/browser-kiosk disable
```

Disable refuses to remove modified installed files, stops the kiosk, locks its
account, and removes the managed session, policy, and launcher files. It keeps
the account home and Chrome state. It does not remove Sway or restart SDDM.
To restore the managed files and unlock the previously configured kiosk
password, run `pkexec ./scripts/browser-kiosk enable` from the repository.
A new account still requires setting its password interactively. Persistent login state, wallets,
and private account identifiers remain local and must not be committed.

The implementation is in `scripts/browser-kiosk`, `config/kiosk/sway.conf`, and
`tests/test_browser_kiosk.py`. Installation is explicitly opt-in; the normal
Kubuntu profile does not silently provision another login account.

## Resolved startup issues

The first physical startup failed because Sway selected the proprietary
NVIDIA device, leaving a blank screen. The launcher now prefers the Intel GPU
when available. Recovery activated the owner's existing locked session; SDDM
was not restarted. A subsequent trial started Sway and Chrome successfully.

The first exit attempt was rejected because pkexec inherited
`SHELL=/usr/sbin/nologin`. The exit command now supplies `/bin/sh` only in its
process environment, while the kiosk account retains its `nologin` login
shell. The next physical trial authenticated successfully and returned to the
locked owner session.

Signed-out Photos redirects to `https://www.google.com/photos/about/`, and
narrow sign-in exceptions still broke CAPTCHA. Owner enrollment now temporarily
permits websites. The owner completed sign-in with this mode; the authenticated
exit restored Photos-only navigation and the saved login survived reopening.
