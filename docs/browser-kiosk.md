# Family Photos browser kiosk

Status: prototype failed its first physical startup test on 2026-11-15.
Do not re-enable for handoff until independent automatic recovery is implemented
and tested. Sway rejected the proprietary NVIDIA device; the session launcher
now prefers Intel graphics when available, but this fix has not passed a physical
retry. The failed attempt left a blank screen. Recovery required activating the
owner’s already-locked session from the existing agent. SSH recovery was not
verified and the user reported it unavailable during the incident.

The managed kiosk uses a separate `photos-kiosk` Linux user, a minimal Sway
session, and mandatory Chrome policies scoped to that account. Its browser
profile persists locally. It contains no personal Chrome profile, desktop
panel, launcher, or terminal shortcut. Ctrl+Alt+Backspace requests administrator
authentication to end the session; cancelling keeps the session running.

Sway replaces Cage from the [original research](browser-kiosk-research.md)
because the exit shortcut needs a system authentication prompt. The private
configuration does not include the distribution's normal Sway desktop config.
The only configured shortcut is the authenticated exit action. Server keys
for virtual-terminal switching are disabled through the XKB configuration.

Implementation and automated checks do not constitute physical acceptance.
Until the checks below have passed on the target computer, treat this as a
prototype and do not hand it to an untrusted guest.

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

Enrollment mode permits the Google Accounts sign-in host and `chrome://policy`
in addition to Photos. It ends any existing kiosk session. Sign in through the
normal login screen as `photos-kiosk`, select **Family Photos kiosk**, and
interactively sign into the intended family Google account. Verify the exact
account; no identifier or password is stored in this repository.

Use Ctrl+Alt+Backspace and authenticate as an administrator to end enrollment.
Normal `stop` resets the policy to Photos only before ending the session. An
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
Reinstall through the repository script to restore the managed files, then set
the kiosk login password again if necessary. Persistent login state, wallets,
and private account identifiers remain local and must not be committed.

The implementation is in `scripts/browser-kiosk`, `config/kiosk/sway.conf`, and
`tests/test_browser_kiosk.py`. Installation is explicitly opt-in; the normal
Kubuntu profile does not silently provision another login account.
