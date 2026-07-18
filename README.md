# SANCTUM

**A protected place for serious work.**

Sanctum OS is a hardened, minimal Debian 13 derivative for aarch64, purpose-built
for secure AI work inside virtual machines on Apple Silicon. It boots in
VirtualBox 7.2+ ARM64 VMs, installs with LUKS2 full-disk encryption by default,
ships a deliberately small GNOME 48 desktop, and provisions Claude Desktop from
Anthropic's official signed repository on first boot.

Version 1.0.0 — codename *marble*.

---

## What ships

### Security, by default

| Layer    | What you get |
| -------- | ------------ |
| Disk     | LUKS2 full-disk encryption, pre-selected in the installer; passphrase required at every boot |
| Network  | nftables deny-all-inbound firewall, encrypted DNS (Quad9, DNS-over-TLS + DNSSEC), LLMNR/mDNS off, Wi-Fi MAC randomization, zero listening services, no SSH |
| Kernel   | `lockdown=integrity`, KSPP-aligned sysctls, hardened boot command line, module blacklist for legacy protocol and bus drivers |
| System   | AppArmor enforced, root account locked, no core dumps, zram-only swap (secrets never swap to disk), `0700` home directories, `027` umask |
| Apps     | Firefox and Telegram as Flatpaks in bubblewrap sandboxes with tightened permission overrides; Firefox telemetry disabled by enterprise policy |
| Updates  | Automatic security updates via unattended-upgrades (Debian security + Claude Desktop), daily automatic Flatpak updates |
| Supply chain | Anthropic's apt signing key fingerprint is pinned at image build time — the build fails on any mismatch |

The complete inventory, including what we deliberately did *not* harden and why,
is in [docs/SECURITY.md](docs/SECURITY.md).

### The app set

Small on purpose. GNOME Shell, Console, Files, and Settings; Firefox; Telegram;
and Claude Desktop, fetched from Anthropic's official repository the first time
the installed system has network. Nothing else competes for your attention.

### The design

Light mode only. Warm white surfaces, ink text, a single slate-blue accent.
Inter for the interface, JetBrains Mono for the terminal. The aperture glyph —
two rings and a point — marks the system from boot splash to installer.

## Requirements

- Apple Silicon Mac (M1 or later) running macOS
- [VirtualBox 7.2.12 or newer](https://www.virtualbox.org/wiki/Downloads) (the Apple Silicon build)
- A VM with 4+ GB RAM, 4 CPUs, and 25 GB of disk (the defaults our script sets)

UTM/QEMU works as a fallback with the same ISO — see
[docs/VIRTUALBOX.md](docs/VIRTUALBOX.md#appendix-utm-fallback).

## Quick start

1. **Get the ISO.** Download `sanctum-os-1.0.0-arm64.iso` and `SHA256SUMS` from
   the [Releases](../../releases) page (or from any green run under
   [Actions](../../actions), as the `sanctum-os-iso` artifact). Verify it:

   ```sh
   shasum -a 256 -c SHA256SUMS
   ```

2. **Create the VM.** Clone this repository and run the creation script — it
   encodes every known-good VirtualBox ARM64 setting (UEFI, VMSVGA graphics,
   VirtIO SCSI storage):

   ```sh
   ./build/vbox-create.sh ~/Downloads/sanctum-os-1.0.0-arm64.iso
   VBoxManage startvm "Sanctum OS"
   ```

3. **Install.** Boot the live session, open **Install Sanctum OS**, choose an
   encryption passphrase, and follow the installer. The full walkthrough is in
   [docs/INSTALL.md](docs/INSTALL.md).

## Repository layout

```
sanctum-os/
├── .github/workflows/build-iso.yml   CI: native arm64 ISO build, artifact upload, tagged releases
├── Makefile                          convenience targets: iso, assets, vm-create, vm-destroy
├── VERSION                           the single source of the version number
├── branding/                         SVG-only brand sources + rasterize.manifest (no binaries committed)
├── build/
│   ├── build.sh                      ISO build entrypoint (runs inside a Debian trixie environment)
│   ├── container-build.sh            local build via OrbStack/Docker on the Mac
│   ├── mkassets.sh                   rasterizes SVGs to PNGs per the manifest
│   └── vbox-create.sh                creates a correctly configured VirtualBox ARM64 VM
├── config/                           the live-build tree
│   ├── auto/config                   image definition: Debian 13, arm64, GRUB-EFI, squashfs
│   ├── package-lists/                what gets installed: base, desktop, installer, VM support
│   ├── hooks/normal/                 build-time customization scripts, run inside the chroot
│   └── includes.chroot/              files overlaid verbatim onto the image's /
└── docs/                             BUILD, INSTALL, SECURITY, ARCHITECTURE, VIRTUALBOX
```

## Building from source

The ISO reproduces from this repository alone — on a GitHub Actions arm64
runner, or locally in about half an hour with OrbStack or Docker:

```sh
./build/container-build.sh
```

Details, including how the live-build stages fit together and how the SVG asset
pipeline works, are in [docs/BUILD.md](docs/BUILD.md).

## License and trademarks

Sanctum OS build scripts and configuration are released under the
[MIT License](LICENSE).

Sanctum OS is an independent project. It is not affiliated with, endorsed by, or
sponsored by Anthropic, the Debian Project, the GNOME Foundation, or Oracle.
Claude, Debian, GNOME, and VirtualBox are trademarks of their respective owners.
Claude Desktop is **not** redistributed in the ISO: the image carries only
Anthropic's public signing key (fingerprint-pinned at build time) and the
application is downloaded from Anthropic's official repository on the first boot
with network, under Anthropic's own terms.
