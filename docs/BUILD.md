# Building the Sanctum OS ISO

The image is fully reproducible from this repository: every asset is text (SVG,
shell, config), every binary is fetched from Debian, Flathub, or Anthropic at
build time, and nothing binary is committed. The build must run **natively on
aarch64** — `build/build.sh` refuses anything else. That gives you two paths.

## Path 1 — GitHub Actions (recommended)

The workflow at `.github/workflows/build-iso.yml` builds on GitHub's free
native arm64 runners (`ubuntu-24.04-arm`) inside a privileged `debian:trixie`
container. No emulation, no cross-compilation.

1. Fork (or push) this repository to GitHub as a **public** repo — the free
   arm64 runners are for public repositories.
2. Push to `main`, or trigger the **Build Sanctum OS ISO** workflow manually
   from the Actions tab (`workflow_dispatch` is enabled).
3. Wait 20–40 minutes. The run uploads two artifacts:
   - `sanctum-os-iso` — the ISO plus `SHA256SUMS`
   - `build-log` — the full live-build log, uploaded even on failure

The workflow has a 120-minute timeout and `contents: write` permission for the
release step (below).

## Path 2 — local build on the Mac

Requires a container runtime — [OrbStack](https://orbstack.dev)
(`brew install --cask orbstack`) or Docker Desktop — plus roughly **15–20 GB of
free disk** and 20–40 minutes:

```sh
./build/container-build.sh
```

or, equivalently:

```sh
make iso
```

This runs a privileged `linux/arm64` `debian:trixie` container with the
repository mounted at `/sanctum` and executes `build/build.sh` inside it.
Privileged mode is required: live-build loop-mounts filesystems and chroots.
Apple Silicon runs the arm64 container natively, so the build is full speed.

The result lands in `dist/`:

```
dist/sanctum-os-1.0.0-arm64.iso
dist/SHA256SUMS
```

To start over cleanly, `make clean` removes `dist/` and the log; the live-build
working directories (`chroot/`, `binary/`, `cache/`, …) are recreated inside
the container on each run and are `.gitignore`d.

## What the build actually does

`build/build.sh` is the whole pipeline:

1. **Asserts aarch64.** Fails immediately on any other architecture.
2. **Installs build dependencies** (`live-build`, `xorriso`, `squashfs-tools`,
   `librsvg2-bin`, and friends) into the throwaway container.
3. **Rasterizes branding** via `build/mkassets.sh` (see below).
4. **Runs live-build**: `lb clean --purge`, `lb config`, `lb build`.
5. **Names and checksums** the output into `dist/`.

### How the live-build stages fit together

live-build assembles the image in layers; each layer of this repository maps to
one stage:

| Stage | Where it lives here | What happens |
| ----- | ------------------- | ------------ |
| Configuration | `auto/config` | Defines the image: Debian 13 (trixie), `arm64`, live system, `iso-hybrid`, **GRUB-EFI bootloader** (ARM64 VMs are UEFI-only — there is no BIOS/syslinux path), squashfs root, boot parameters for the live session (`username=sanctum`, `hostname=sanctum`, …) |
| Bootstrap + packages | `config/package-lists/*.list.chroot` | debootstrap builds a minimal trixie chroot, then installs the four package lists: `sanctum-base` (security backbone), `sanctum-desktop` (minimal GNOME 48), `sanctum-installer` (Calamares + crypto/boot stack), `sanctum-vm` (VirtualBox/UTM guest support) |
| File overlay | `config/includes.chroot/` | Copied verbatim onto the chroot's `/`. This is where the firewall rules, sysctls, DNS config, systemd units, provisioning scripts, and branding assets live |
| Hooks | `config/hooks/normal/*.hook.chroot` | Shell scripts executed **inside** the chroot, in numeric order: `0100` identity (os-release), `0200` pin Anthropic's apt key (build fails on fingerprint mismatch), `0300` install Firefox + Telegram Flatpaks and tighten their sandboxes, `0500` compile dconf defaults + set the Plymouth theme, `0600` service enable/mask policy, `0700` account hardening, `0900` cleanup and slimming |
| Binary | (generated) | The chroot is compressed into a squashfs, wrapped with GRUB-EFI (`BOOTAA64.EFI`), and mastered into the hybrid ISO |

`auto/build` wraps `lb build` and tees everything to `build.log`;
`auto/clean` resets the generated state.

## The asset pipeline

No PNG, ICO, or any other binary is committed. Brand sources are SVGs under
`branding/`, and `branding/rasterize.manifest` declares every raster the image
needs, one per line:

```
<svg source> <png output> <width> <height>
```

Paths are repo-root-relative; `#` lines are comments. `build/mkassets.sh` walks
the manifest with `rsvg-convert` and **fails the build if any source is
missing**. The PNG outputs (wallpapers, Plymouth theme, GRUB splash, Calamares
branding) are listed in `.gitignore` — they exist only inside a build.

To rasterize locally without a full build (useful when iterating on branding):

```sh
brew install librsvg
make assets
```

## Versioning and releases

`VERSION` at the repository root is the single source of truth; `build/build.sh`
reads it to name the ISO. The release flow:

1. Update `VERSION` (and, for a version bump, `VERSION_ID` in
   `config/hooks/normal/0100-identity.hook.chroot`, which stamps
   `/etc/os-release`).
2. Commit, then tag and push:

   ```sh
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. The same workflow builds the ISO and — because the ref matches `v*` —
   publishes a GitHub Release with the ISO, `SHA256SUMS`, and generated notes.

Pushes to `main` without a tag still build and upload the artifact, so every
merge is proven buildable.
