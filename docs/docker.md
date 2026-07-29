# Docker

## Ownership

The `kubuntu-laptop`, `wsl-personal`, and `wsl-work` profiles install native
Docker Engine from Docker's official stable Ubuntu APT repository. The managed
packages are Docker CE, its CLI, containerd, Docker Compose, and Buildx.

This is deliberately not Docker Desktop. The WSL profiles run Docker inside
Ubuntu using WSL 2 and systemd. Homebrew does not own the Docker CLI in these
profiles.

## Apply and update

```bash
dot apply --profile kubuntu-laptop --tags docker
dot update --profile kubuntu-laptop
dot doctor --profile kubuntu-laptop
```

Substitute `wsl-personal` or `wsl-work` when inside that distribution. Apply
verifies Docker's signing-key fingerprint before configuring the repository,
installs the latest stable package candidates, enables Docker and containerd,
and adds the current user to the `docker` group. It preserves Docker data and
configuration directories.

Log out and back in after the first Kubuntu apply. In WSL, run `wsl --shutdown`
from PowerShell and reopen the distribution. This activates the new group in a
fresh session.

## WSL prerequisites

Native Docker requires WSL 2 and systemd. Modern Ubuntu installed by current
WSL releases normally enables systemd. For an older distribution, ensure WSL is
current and configure `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

Then run this in PowerShell:

```powershell
wsl --update
wsl --shutdown
```

Docker Desktop WSL integration must be disabled for the managed distribution.
The role checks whether the distribution's active CLI or Docker socket resolves
into Docker Desktop's WSL mount and stops before package changes if so. Merely
having Docker Desktop installed on Windows does not trigger this guard. In
Docker Desktop, open **Settings > Resources > WSL Integration** and disable the
distribution, then shut WSL down before retrying.

## Security

The `docker` group can control a root-owned daemon and is effectively
root-equivalent. These personal workstation profiles intentionally trade that
privilege for convenient local development. Do not copy this policy unchanged
to an untrusted multi-user host.

Docker-published ports can bypass uncomplicated firewall assumptions. Review
Docker's firewall guidance before treating a local firewall as protection for
published container services.

Official references:

- <https://docs.docker.com/engine/install/ubuntu/>
- <https://docs.docker.com/desktop/features/wsl/>
- <https://learn.microsoft.com/windows/wsl/systemd>
