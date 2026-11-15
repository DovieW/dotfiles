# Browser kiosk for Google Photos

Research date: 2026-11-15. Status: proposed design; no kiosk account, packages,
browser policies, or login configuration have been installed by this work.

The intended use is to hand this Kubuntu laptop to someone with access to one
separate family Google Photos account. The guest should have no ordinary
desktop, access to other websites, or access to the owner's session without
the owner's system password. Preserve the family account's login between uses.
Keep account identifiers and credentials outside this public repository.

The recommended foundation is a dedicated unprivileged Linux account running
Google Chrome under Cage, with mandatory browser policies and a protected
session entry and exit workflow. This is a small configuration project, not a
single Chrome setting. The integration and escape tests are the substantial
work; installing Cage is straightforward on the inspected machine.

## What was verified locally

Read-only inspection found Ubuntu 26.04.1, Plasma 6.6.6 on Wayland, SDDM 0.21,
and Google Chrome stable 154.0.8037.97. Cage is not installed; the configured
APT cache offers 0.2.1-1. An `apt-get -s --no-remove install cage` simulation
would add only Cage, with no package removals or upgrades. Its package is about
23 KB downloaded and 77 KiB installed; dependencies are already present.
These are cache observations, not a refreshed upstream release inventory.

The owner's home has mode 0750 with no extended ACL, and the Chrome profile
directory has mode 0700. A new unrelated user would not have ordinary access
to that profile. The display hardware includes Intel and NVIDIA GPUs; a real
SDDM/Cage session, scaling, external displays, and resume still need testing.

The existing Chrome task is `ansible/tasks/chrome.yml`. Normal Chrome launchers
in `config/chromium/` include owner-specific behavior. A kiosk should invoke
the packaged browser with its own profile, not reuse the owner's launcher,
profile, session bus, clipboard manager, or desktop autostarts.

## Alternatives and effort

These are engineering estimates, not measured implementation times.

| Approach | Suitability for this laptop | Estimated effort |
| --- | --- | --- |
| Chrome Guest mode or `--kiosk` inside the owner's desktop | Isolates some browser state or hides browser controls, but leaves the host desktop available. Does not satisfy the requirement. | Minutes for the incomplete demonstration |
| Separate account with a restricted Plasma desktop | Possible, but requires maintaining restrictions across the launcher, shortcuts, desktop services, dialogs, and Chrome. | Several hours, with a broad regression surface |
| Separate account with Cage and Chrome policies | Best fit for occasional handoff on the existing Kubuntu installation. Password-protected return and session enforcement still need integration. | A few hours for a prototype; roughly 1–2 working days for the requested reusable, tested setup |
| GNOME Kiosk or Ubuntu Frame | Valid kiosk foundations, but introduce a different desktop or appliance stack here. | Comparable integration effort; more components to introduce |
| Dedicated kiosk OS or separate device | Better fit for a permanent public terminal than switching this daily-use laptop temporarily. | Installation, account setup, hardware validation, and ongoing maintenance |
| Virtual machine | Can strengthen isolation of browser activity, but a VM window alone does not stop access to the host desktop. A restricted host session is still needed. | More setup, memory, and update work than the direct approach |

[Cage](https://www.hjdskes.nl/projects/cage/) presents applications maximized
without ordinary window management or virtual desktops. Its
[manual](https://github.com/cage-kiosk/cage/blob/v0.2.1/cage.1.scd) makes virtual
terminal switching opt-in with `-s`; omit that option. Debug builds have an
exit shortcut, so verify the packaged build and actual keyboard behavior.
Cage can display additional clients: it is not an executable allowlist or a
complete security sandbox by itself.

KDE's own [Kiosk framework](https://develop.kde.org/docs/administration/kiosk/introduction/)
can restrict KDE applications, but its URL restrictions do not govern Chrome.
[GNOME documents a single-application session](https://help.gnome.org/system-admin-guide/lockdown-single-app-mode.html),
while [Ubuntu Frame](https://ubuntu.com/frame) targets fullscreen embedded
applications. Neither removes the need for browser and account restrictions.

[Porteus Kiosk](https://porteus-kiosk.org/parameters.html) includes browser URL
allowlisting. Its current [subscription terms](https://porteus-kiosk.org/automatic-updates.html)
list a 30-day trial and EUR 40 per PC per year, excluding VAT, for 1–10 PCs;
continued use requires a subscription. Cage plus locally managed Chrome
policies does not require that subscription or new hardware.

## Proposed session behavior

1. The owner starts a Photos session through a normal launcher or login flow.
   Lock and verify the owner's existing graphical session before handing over
   the screen. Leave its applications running. A successful lock request alone
   is insufficient: logind asks the desktop to lock, so verify acknowledgement
   and actual behavior. See the [logind interface](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html).
2. A dedicated account with its own home, runtime directory, and Chrome profile
   runs Cage directly as a separate graphical login. It must not run nested
   inside the owner's desktop. Give it no sudo, Docker, libvirt, owner-home,
   SSH-agent, or other privileged group access.
3. Launch only Chrome and the explicitly required session services. Do not
   start Plasma, KRunner, a terminal, the owner's clipboard tools, or a desktop
   notification service. Deny browser notifications with policy. Check for
   owner-session audio and lock-screen information exposure separately.
4. Enforce the permitted session for the kiosk account. Merely remembering
   "Cage" in the login screen is not enforcement: choosing Plasma must not
   produce a normal desktop. Restrict alternate SSH/console login paths too.
5. A root-owned supervisor running as the kiosk user relaunches Chrome after
   closure or a recoverable crash, with retry limits and a safe failure state.
   Neither browser nor compositor failure may expose an unlocked owner desktop
   or a terminal.
6. Returning to the owner's desktop requires the existing system login or
   unlock authentication. A hidden key combination is not authentication.
   The owner-control path must be designed and tested before disabling escape
   shortcuts; it must not store the owner's password or require restarting
   SDDM. An authentication screen can be reachable without granting access to
   another session. If even reaching that screen must be prevented, gate the
   kiosk stop action itself through system authentication.

SDDM provides configurable session launch wrappers. Its
[configuration manual](https://github.com/sddm/sddm/blob/v0.21.0/data/man/sddm.conf.rst.in)
and [session implementation](https://github.com/sddm/sddm/blob/v0.21.0/src/helper/UserSession.cpp)
support an account-specific guard in a root-owned wrapper. This remains a
design to prototype against the distro's installed version. Check identity
using the actual UID, enforce both available session types, and delegate all
other accounts to the original wrapper. The kiosk branch must not source
guest-writable shell startup files. Do not modify PAM or global login behavior
without reviewing and testing the exact changes and a recovery path.

Use normal password login where wallet unlocking is required. Do not introduce
temporary SDDM autologin or weaken KDE Wallet. Preserve the browser's sandbox;
`--no-sandbox` is not an acceptable workaround for launch problems.

## Chrome policy isolation

Google Chrome's Linux policy directory is
`/etc/opt/chrome/policies/managed/`. It is normally shared by all Chrome users.
A separate Linux user or `--user-data-dir` does not create a separate policy
directory. Installing a globally readable deny-all policy would restrict the
owner's Chrome too. See [Chromium's Linux administration guide](https://www.chromium.org/administrators/linux-quick-start/).

The smallest candidate for this machine is a root-owned kiosk policy file
readable only by a dedicated kiosk group, for example owner `root`, group
`photos-kiosk`, mode `0640`, in root-owned policy directories the guest cannot
write.
Only the kiosk account belongs to that group; the owner's Chrome cannot read
the file. The [policy loader matching installed Chrome 154](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/core/common/config_dir_policy_loader.cc)
skips files it cannot read. Therefore permission-based scoping is a plausible
implementation, inferred from source, not a documented per-user Chrome policy
feature or a runtime-tested result here.

Prove that candidate in an isolated test environment before using it on the
live machine: kiosk Chrome must load the policy as mandatory, owner Chrome
must remain unaffected, and guest processes must be unable to replace or
modify the policy. Check file permissions and both identities after updates.
Do not temporarily expose a world-readable deny-all file during installation.

If this approach proves unsuitable, give the kiosk a private mount namespace
with its own read-only policy directory, or use a separate maintained browser
installation with a distinct policy path. Namespace integration must retain
Chrome's sandbox and work with the session and graphics stack. The configured
Ubuntu `chromium-browser` package is a Snap transition package, so changing to
Chromium is a packaging choice, not just renaming the executable. A second
Chrome profile alone does not solve policy scoping.

## Website and browser restrictions

Use mandatory `URLBlocklist` and `URLAllowlist` policies with default-deny
navigation and an exact HTTPS Google Photos host exception. For example,
`https://.photos.google.com` uses Chrome's leading-dot syntax to exclude
subdomains. This is a starting point, not a complete tested policy. Never
allow the whole `google.com` domain just to make sign-in work: host rules
without the dot also match subdomains. See Google's
[URL filter format](https://support.google.com/chrome/a/answer/9942583?hl=en).

Two limitations materially affect the design:

- The [Chrome 154 URLBlocklist definition](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/URLBlocklist.yaml)
  says `*` does not cover internal `chrome://` pages from version 147 onward.
  Internal surfaces need explicit treatment and relevant feature policies;
  indiscriminate internal-page blocking can cause errors. Prefer specific
  feature restrictions and test any additional internal URL rules.
- The same policy does not constrain all JavaScript data requests or
  same-document History API changes. It is browser navigation control, not a
  network firewall or a reliable way to make one part of an authenticated web
  application read-only. Google recommends stronger filtering when basic
  [URL management](https://support.google.com/chrome/a/answer/7532419?hl=en)
  is insufficient.

Do not invent a broad allowlist of Google asset domains. Measure the actual
Photos navigation, authentication, images, and video behavior during setup.
Image/API resource traffic is a different concern from allowed page
navigation. If all outbound traffic must be constrained, add a separately
enforced proxy/network policy and measure dependencies, including redirects
and alternate transport paths; this adds work and maintenance.

These policy values were checked against Chromium's Chrome 154 definitions:

| Control | Proposed policy |
| --- | --- |
| Developer tools and inspection shortcuts | [`DeveloperToolsAvailability: 2`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/DeveloperToolsAvailability.yaml); also account for `view-source:` navigation |
| Downloads | [`DownloadRestrictions: 3`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/DownloadRestrictions.yaml) |
| File chooser dialogs, uploads, Save As | [`AllowFileSelectionDialogs: false`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/AllowFileSelectionDialogs.yaml) |
| Printing, including the print-to-PDF route | [`PrintingEnabled: false`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Printing/PrintingEnabled.yaml) |
| Website desktop notifications | [`DefaultNotificationsSetting: 2`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/ContentSettings/DefaultNotificationsSetting.yaml) |
| Additional Chrome profiles and browser Guest mode | [`BrowserAddPersonEnabled: false`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/BrowserAddPersonEnabled.yaml), [`BrowserGuestModeEnabled: false`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/BrowserGuestModeEnabled.yaml) |
| Browser account sign-in and sync | [`BrowserSignin: 0`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Miscellaneous/BrowserSignin.yaml); website sign-in remains available |
| Extension installation | [`ExtensionSettings`](https://github.com/chromium/chromium/blob/154.0.8037.97/components/policy/resources/templates/policy_definitions/Extensions/ExtensionSettings.yaml) with default installation mode `blocked`; inspect any overriding exceptions |

Download blocking alone excludes saving the displayed page and printing to
PDF; that is why the file-dialog and printing restrictions are separate.
Also review incognito entry points, password saving, popups, external protocol
handlers, browser task manager, permissions, desktop portals, and account
switching. Do not mistake a hidden menu for an enforced restriction, or a
ChromeOS-only policy for Linux support.

## The family Google Photos account

Sign into the intended family account interactively in the kiosk's clean
profile. Verify the account identifier during setup; do not guess it or copy
an existing personal Chrome profile. Keep its cookies and any credential-store
state local, private, and persistent. Browser sign-in can be disabled while
Photos website sign-in remains available; these are different mechanisms.

URL policies do not by themselves enforce a particular consumer Google web
account identity. After owner-controlled sign-in, restrict account-addition
and sign-in navigation as far as the measured flow permits. If authentication
expires, stop at an owner-maintenance state rather than widening access for
the guest. Test sign-out and account-switcher behavior explicitly.

An authenticated Photos account retains its in-app capabilities: viewing the
library can also permit editing, deletion, sharing, and changes within Photos.
The kiosk must not be described as read-only. If that becomes a requirement,
use selected albums viewed without the owning account, or a separate viewing
account with appropriately shared content. Google documents
[shared-album controls](https://support.google.com/photos/answer/9789702?hl=en)
and how to disable [collaboration and comments](https://support.google.com/photos/answer/6280921?co=GENIE.Platform%3DDesktop&hl=en).
Anyone who obtains a shared link can view its content, so keep such links out
of the public repository. No kiosk prevents photographing its screen.

## Acceptance tests before handoff

- Verify the kiosk UID, lack of privileged groups, private home/profile, and
  absence of owner sockets, credentials, files, and clipboard data.
- Confirm mandatory policy values and status in `chrome://policy` through an
  owner-controlled inspection path. Prove the owner's Chrome is unaffected.
- Try other websites, Gmail, Drive, Search, local files, internal Chrome pages,
  redirects, new tabs/windows, incognito, developer tools, downloads, printing,
  uploads, account changes, and external app links. Exercise Photos images,
  videos, fullscreen, and authentication expiry.
- Try Alt+Tab, Super, Alt+F2, Ctrl+Alt+T, Alt+F4, Alt+Escape, F11,
  Ctrl+W, Ctrl+Shift+W, Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+P, Ctrl+Shift+I,
  Ctrl+Alt+function keys, touchpad gestures, and mouse context menus.
- Attempt selecting a normal Plasma session for the kiosk account and alternate
  login routes. Check guest-specific polkit permissions for mounts, network
  changes, power actions, and session operations; absence of a prompt agent is
  not a permissions boundary.
- Close and crash Chrome, terminate the compositor, disconnect networking,
  suspend/resume, reconnect displays, and reboot. Every failure must preserve
  the owner's lock and avoid an unrestricted guest shell or desktop.
- Verify that returning to the owner's usable desktop requires the owner's
  password. Test both correct and incorrect authentication, cancellation, and
  the recovery path. Verify notifications and any audio do not expose owner
  information during handoff.
- Recheck after Chrome, Cage, SDDM, or policy changes. Keep the browser sandbox
  enabled and distinguish on-disk updates from the code a running kiosk uses.

The intended assurance is resistance to normal UI and keyboard escape attempts
with account isolation. It is not a guarantee against browser/kernel exploits,
forced power-off, or alternate boot media. If unattended hostile physical
access is in scope, review disk encryption, firmware/boot controls, and a
dedicated kiosk device separately. Never weaken the owner's recovery setup
just to hide a shortcut.

## Keeping the method reproducible

Add the implementation as an optional dotfiles feature after the prototype
passes. Proposed locations, not existing functionality:

- `ansible/tasks/browser-kiosk.yml`: packages, account/groups, root-owned
  policy and launch files, and narrowly scoped session restrictions.
- `config/kiosk/`: generic policy templates, session entry, and supervisor
  configuration, with no account identifiers or live album links.
- `scripts/browser-kiosk`: owner-facing launch, stop, status, and diagnostic
  actions, using standard system authentication instead of storing passwords.
- Profile/schema support for opting into the feature, plus tests for policy
  scope, forced sessions, failure behavior, and removal.
- This guide: setup, actual validated behavior, limitations, updates, and
  rollback instructions after implementation.

The final interface should offer a normal desktop launcher such as "Family
Photos guest session." Its allowlist should be configurable for future uses.
Store credentials, cookies, exact account identifiers, and private URLs in
local protected state. Reinstallation should rebuild the environment and
request interactive account enrollment, not restore secrets from Git.

Check mode must not switch sessions, restart Chrome, or change login state.
Apply and removal must preserve the owner's open work and existing login
configuration. Keep kiosk state when disabling the feature unless its deletion
is explicitly requested. Reuse the post-update process audit where activation
handling is added; refresh only verified kiosk-owned processes when safe and
report any remaining restart requirements. Commit and push durable changes
after the relevant validation.
