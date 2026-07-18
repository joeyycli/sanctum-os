# Sanctum OS on VirtualBox (Apple Silicon)

Everything VirtualBox-specific in one place: what the ARM port can and cannot
do, the settings that work, Guest Additions, and the UTM fallback.

Baseline: **VirtualBox 7.2.12 or newer**, the macOS/Apple Silicon build.
Keep VirtualBox itself updated — Sanctum can patch the guest, never the
hypervisor.

## Known limitations of VirtualBox on ARM

The ARM port is newer than the x86 one and several familiar features simply do
not exist yet. Knowing them up front saves debugging time:

- **ARM64 guests only.** There is no x86/amd64 emulation. An amd64 ISO will
  not boot — it drops the VM to a UEFI shell (see troubleshooting in
  [INSTALL.md](INSTALL.md#troubleshooting)).
- **UEFI only.** ARM VMs have no BIOS option. Anything you boot must carry an
  EFI loader (Sanctum's ISO does: GRUB as `BOOTAA64.EFI`).
- **VMSVGA is the only graphics controller.** Other controller choices give a
  black screen.
- **No 3D acceleration for Linux guests.** GNOME renders with software
  (llvmpipe). Sanctum's desktop is deliberately restrained partly for this
  reason — it stays responsive without GPU compositing. Do not enable the 3D
  acceleration checkbox; it does nothing useful for ARM Linux guests.
- **Drag-and-drop between host and guest does not work** on the ARM port,
  even with Guest Additions. Use the shared clipboard (works after Guest
  Additions) or a shared folder instead.
- **Audio passthrough is unreliable** for ARM guests; Sanctum's VM script
  disables the audio device entirely.
- **Snapshots of a running VM capture guest RAM** — including disk-encryption
  keys. Prefer powered-off snapshots for a hardened guest (see below).

## Recommended VM settings

These are exactly what `build/vbox-create.sh` configures; use this table if
you create the VM by hand.

| Setting | Value | Notes |
| ------- | ----- | ----- |
| Platform / OS type | ARM, `Debian_arm64` | Selects the ARM virtualization stack |
| Memory | 4096 MB (minimum 2048) | GNOME + Firefox + Claude Desktop are comfortable at 4 GB |
| CPUs | 4 | Performance cores are plentiful on Apple Silicon |
| Graphics controller | **VMSVGA** | The only working option |
| Video memory | **128 MB** (maximum) | Low VRAM causes blank screens and missing resolutions |
| Storage controller | **VirtIO SCSI** | Disk on port 0, optical (ISO) on port 1 |
| Disk | 25 GB VDI | LUKS container + system + working space |
| Network adapter | NAT | Outbound-only; matches the guest's deny-inbound firewall |
| Audio | None | Unreliable on ARM guests; removed surface |
| USB | xHCI (USB 3.0) | Virtual input devices |
| Clipboard | Bidirectional | Functional only after Guest Additions; a privacy trade-off — see [SECURITY.md](SECURITY.md#what-we-deliberately-did-not-do--and-why) |

Reproduce all of it with:

```sh
./build/vbox-create.sh path/to/sanctum-os-1.0.0-arm64.iso
```

## Guest Additions

Oracle ships ARM64 Guest Additions as `VBoxLinuxAdditions-arm64.run` on the
Guest Additions CD image; they compile kernel modules on install. Sanctum
preinstalls the whole toolchain (`dkms`, `build-essential`,
`linux-headers-arm64`) and a helper so the process is:

1. VirtualBox menu bar: **Devices ▸ Insert Guest Additions CD image…**
2. In the guest:

   ```sh
   sudo sanctum-vbox-additions
   ```

3. Reboot the VM.

The helper (`/usr/local/bin/sanctum-vbox-additions`) finds the run-file on the
mounted CD (mounting `/dev/sr0` itself if the desktop didn't), executes it, and
tolerates the installer's benign non-zero exits. After the reboot you have
bidirectional clipboard and displays that resize with the VM window.

DKMS rebuilds the modules automatically when kernel updates arrive via
unattended-upgrades. After a **VirtualBox** upgrade, re-run the two steps above
so the Additions match the new host version.

## Snapshots across VirtualBox upgrades

Two cautions, one specific to hardened guests:

- **Across major VirtualBox upgrades (7.2 → 7.3 and beyond), running-state
  snapshots are not reliably restorable** — the saved device state may not
  match the new version's virtual hardware. Before upgrading VirtualBox: shut
  the guest down fully (not saved-state), and either delete running-state
  snapshots or accept that you may have to discard their memory state.
  Powered-off snapshots (disk-only) survive upgrades fine.
- **A running-state snapshot contains the guest's RAM**, and therefore the
  LUKS volume keys of the unlocked disk. Store snapshots only on a
  FileVault-protected host disk, and prefer snapshotting while the VM is
  powered off.

## Appendix: UTM fallback

The same ISO runs under [UTM](https://mac.getutm.app) (QEMU) if you prefer it
or need to compare behavior. Sanctum preinstalls `spice-vdagent` and
`qemu-guest-agent`, so clipboard sharing and display resize work **without any
Guest Additions step** — UTM's integration is native.

Create the VM like this:

1. UTM ▸ **Create a New Virtual Machine** ▸ **Virtualize** (not Emulate — we
   want Apple's hypervisor at native speed).
2. **Linux**. Leave "Use Apple Virtualization" unchecked (use QEMU), and do
   not enable Rosetta.
3. **Boot ISO Image**: select `sanctum-os-1.0.0-arm64.iso`.
4. Hardware: 4096 MB RAM, 4 CPU cores. Leave hardware OpenGL acceleration
   off (same llvmpipe situation as VirtualBox).
5. Storage: 25 GB.
6. Save, then before starting: in the VM settings, set **Display** to
   `virtio-gpu-pci`. Avoid the `-gl` variants for the installer; you can
   experiment after installing.
7. Boot, install, and use it exactly as described in
   [INSTALL.md](INSTALL.md) — skip step 5 (Guest Additions), which is
   VirtualBox-only. Clipboard and resize already work via SPICE.

The guest is identical in both hypervisors: same ISO, same hardening, same
first-boot provisioning.

## Claude Desktop shows a blank window?

VirtualBox ARM exposes no GPU render node to Linux guests, and Electron's GPU
compositor produces an empty window on the software-GL fallback. Sanctum ships
a launcher shim (`/usr/local/bin/claude-desktop`) that detects the missing
`/dev/dri/renderD128` and adds `--disable-gpu` automatically. If you ever see
a blank Claude window regardless, launch it manually with:

    claude-desktop --disable-gpu
