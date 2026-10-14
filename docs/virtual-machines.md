# Virtual machines on Kubuntu

The Kubuntu laptop and desktop profiles use Ubuntu's KVM/QEMU and libvirt
packages, with **Virtual Machine Manager** (`virt-manager`) as the interface.
There is no custom VM CLI. VM creation, hardware settings, start/shutdown, and
the guest display are available in the GUI.

## Install or repair the managed host setup

```sh
dot apply --profile kubuntu-laptop --tags virtualization
```

Use `kubuntu-desktop` on that profile. The targeted apply installs the packages,
grants the interactive user `kvm` and `libvirt` membership, enables socket
activation, and starts/autostarts libvirt's default NAT network. Log out and
back in after the first apply to activate new group membership. Guests do not
start automatically unless you explicitly enable that for a VM in the GUI.
The apply does not recreate a missing default network or overwrite an existing
network's definition; a missing network needs review before redefinition.

Open **Virtual Machine Manager** from the application launcher. Use the
**QEMU/KVM system** connection (`qemu:///system`), rather than QEMU user session.
The system connection gives the GUI access to the managed NAT network.
The managed shell and application launchers explicitly use Ubuntu's Python,
so Homebrew Python on `PATH` cannot hide the packaged GTK/libvirt bindings.
Repair just these launchers with `dot apply --profile kubuntu-laptop --tags virtualization-launcher`.

## Create a Windows 11 VM

1. Download the x64 installation ISO from
   [Microsoft](https://www.microsoft.com/software-download/windows11), and the
   stable [VirtIO Windows driver ISO](https://github.com/virtio-win/virtio-win-pkg-scripts/blob/master/README.md).
2. In Virtual Machine Manager, choose **Create a new virtual machine**, select
   **Local install media**, and select the Windows ISO. Set the OS to Windows 11
   if automatic detection fails.
3. Start with **8192 MiB RAM**, **4 vCPUs**, and a **100 GiB qcow2 disk**. Avoid
   allocating the whole disk up front: a sparse disk grows as data is written.
   Close heavier host apps when available host RAM is below about 12 GiB.
4. Select **Customize configuration before install**. Use a Q35 machine,
   UEFI firmware with Secure Boot and enrolled Microsoft keys, and an emulated
   **TPM 2.0** (CRB model). Check these settings even if the wizard adds them.
5. Use a VirtIO disk and VirtIO network adapter on **default: NAT**. Attach the
   VirtIO driver ISO as a second CD-ROM. Leave the VM autostart option off.
6. Start installation. If Windows cannot see the disk, select **Load driver**
   and browse the VirtIO ISO: `viostor/w11/amd64` for a VirtIO disk, or
   `vioscsi/w11/amd64` for a VirtIO SCSI controller. If networking is missing,
   use the `NetKVM/w11/amd64` driver.
7. After installation, run `virtio-win-guest-tools.exe` from the driver ISO
   for guest drivers and integration. Eject the installer ISOs. Install Cua
   Driver and the chosen agent inside Windows if that is the VM's purpose.

The normal virtual display is intended for desktop apps and browser use. It
does not promise gaming-class Windows graphics; GPU passthrough is a separate
configuration project.

## Storage and everyday use

Keep VM disks in the default system storage pool (`/var/lib/libvirt/images`),
outside this repository. Guest firmware state, virtual TPM state, Windows
accounts, and activation are machine state, not dotfiles. A backup intended to
restore the VM must include its definition, disk, NVRAM and TPM state; a copy of
the qcow2 disk alone may be insufficient.

Use the GUI's **Shut Down** action to stop Windows normally. Closing only the
viewer window leaves the VM running. **Force Off** is equivalent to cutting
power and should be reserved for a stuck guest.

For troubleshooting, the upstream CLI remains available:

```sh
virsh --connect qemu:///system list --all
virsh --connect qemu:///system net-list --all
virt-host-validate qemu
```

References: [Ubuntu libvirt](https://ubuntu.com/server/docs/how-to/virtualisation/libvirt/),
[virt-manager](https://virt-manager.org/), and
[Windows 11 requirements](https://www.microsoft.com/windows/windows-11-specifications).
