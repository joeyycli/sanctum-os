# Installing Sanctum OS

From a downloaded ISO to a working, encrypted system in about fifteen minutes.

## Before you start

- Apple Silicon Mac with [VirtualBox 7.2.12+](https://www.virtualbox.org/wiki/Downloads) installed
- `sanctum-os-1.0.0-arm64.iso` and `SHA256SUMS`, from Releases or an Actions
  artifact — verify first:

  ```sh
  shasum -a 256 -c SHA256SUMS
  ```

## 1. Create the VM

Run the creation script from a clone of this repository:

```sh
./build/vbox-create.sh ~/Downloads/sanctum-os-1.0.0-arm64.iso
```

It registers a VM named **Sanctum OS** with a 25 GB disk, 4096 MB RAM, and
4 CPUs (override with `DISK_GB`, `RAM_MB`, `CPUS` environment variables).
Every setting it applies exists for a reason:

| Setting | Value | Why |
| ------- | ----- | --- |
| Platform architecture | `arm` / `Debian_arm64` | VirtualBox on Apple Silicon virtualizes **ARM64 guests only** — there is no x86 emulation |
| Firmware | UEFI (implicit for ARM VMs) | ARM64 VMs have no BIOS. The ISO boots via GRUB-EFI (`BOOTAA64.EFI`); nothing else would start |
| Graphics controller | `VMSVGA`, 128 MB VRAM | The only graphics controller that works for ARM guests. Maximum VRAM avoids blank-screen and resolution problems |
| Storage controller | VirtIO SCSI (disk on port 0, ISO on port 1) | The paravirtual storage path — fastest and best supported by the Linux kernel in a VM |
| Network | NAT | Outbound-only connectivity, which matches the OS's deny-all-inbound firewall posture |
| Audio | none | No audio stack in the VM; less surface, and ARM guest audio support is unreliable anyway |
| Clipboard | bidirectional | Pre-configured now; it becomes functional only after you install Guest Additions (step 5) |
| USB | xHCI on | Standard USB 3 controller for the virtual keyboard/tablet |

If you prefer to create the VM by hand in the VirtualBox UI, match that table.

Start it:

```sh
VBoxManage startvm "Sanctum OS"
```

## 2. Live boot

GRUB appears briefly, then Sanctum boots into a live GNOME session as the user
`sanctum` — no password, and `sudo` works without one (live session only; the
installed system is stricter). The live session runs entirely from RAM and the
read-only squashfs: nothing you do here persists, which also makes it a safe
place to look around before committing to an install.

## 3. Run the installer

Open **Install Sanctum OS**. Calamares walks you through, in order:

1. **Welcome** — language.
2. **Location** — timezone.
3. **Keyboard** — layout. Note: this layout is also what you will type your
   disk passphrase with at every boot.
4. **Partitions** — choose **Erase disk** (the disk is the empty 25 GB virtual
   disk; there is nothing on it to preserve). Full-disk encryption is
   **pre-selected**: the encrypt option is already checked, and you are asked
   for a passphrase here. This creates a LUKS container holding the entire
   system; only the small EFI partition stays unencrypted, as it must. Choose a
   passphrase you can type reliably — it cannot be recovered, and the VM's disk
   is unreadable without it.
5. **Users** — your name, username, and login password. This account gets
   `sudo`; the root account itself is locked. Home directories are created
   `0700` (private to you).
6. **Summary** — review, then install. Copying the system takes roughly 5–10
   minutes in the VM.
7. **Finish** — check *Restart now*. If the VM boots back into the live
   session instead of your new system, the ISO is still attached: remove it
   under **Devices ▸ Optical Drives** and reset the VM.

### What the passphrase means at boot

Every boot from now on: GRUB (a two-second hidden timeout), then an early-boot
prompt for the LUKS passphrase on the Sanctum splash screen. Nothing —
including your login screen — loads until the disk is unlocked. Type the
passphrase and press Enter; GDM follows. A wrong passphrase just asks again.

## 4. First boot — Claude Desktop provisioning

The ISO does not contain Claude Desktop (Anthropic's terms don't permit
redistributing it). Instead, `sanctum-provision.service` runs on the first boot
and installs it from Anthropic's official apt repository over the pinned
signing key. This means the **first boot needs network once**. With the default
NAT adapter, that's automatic.

- The download and install take a few minutes in the background; the Claude
  Desktop icon appears when it's done.
- If the VM had no network on first boot, nothing is lost: the service retries
  every 30 seconds while boot proceeds, and runs again on the next boot until it
  succeeds. Check on it with:

  ```sh
  systemctl status sanctum-provision.service
  ```

- Once installed, open Claude Desktop and sign in with your claude.ai account.
  Updates arrive automatically through unattended-upgrades, from the same
  signed repository.

## 5. Post-install: Guest Additions

Clipboard sharing and dynamic display resize need VirtualBox Guest Additions,
which Oracle ships as an installer on their own CD image. Sanctum includes a
helper and the whole toolchain (dkms, headers, compiler) so this is two steps:

1. In the VirtualBox menu bar: **Devices ▸ Insert Guest Additions CD image…**
2. In GNOME Console:

   ```sh
   sudo sanctum-vbox-additions
   ```

Reboot when it finishes. Clipboard (bidirectional) and window-resize-follows-VM
now work. Repeat these two steps after major VirtualBox upgrades, which ship
new Additions.

## Troubleshooting

| Symptom | Cause and fix |
| ------- | ------------- |
| VM drops to a yellow `UEFI Interactive Shell` | The firmware found nothing bootable: the ISO is wrong (an x86/amd64 image) or corrupt. Verify with `shasum -a 256 -c SHA256SUMS` and confirm the filename says `arm64`. Type `reset` in the shell after fixing the attached ISO |
| VM fails to boot with less than 1 GiB RAM | A VirtualBox ARM bug, fixed in 7.2.10. Irrelevant at Sanctum's 4 GB default — but don't shrink the VM below 2 GB regardless |
| Blank or black screen at boot | Graphics controller must be **VMSVGA** with VRAM at maximum (128 MB). `VBoxManage modifyvm "Sanctum OS" --graphicscontroller vmsvga --vram 128` with the VM powered off |
| No clipboard sharing / window doesn't resize the display | Guest Additions not installed yet — see step 5. Both features require them |
| Claude Desktop never appears | The first boot had no network, or the download was interrupted. `journalctl -u sanctum-provision.service` shows why; the service re-runs at every boot until it succeeds |
| Forgot the disk passphrase | Unrecoverable by design. Recreate the VM (`make vm-destroy`, then step 1) and reinstall |
