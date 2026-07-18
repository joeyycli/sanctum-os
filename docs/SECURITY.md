# Sanctum OS security model

This document describes what Sanctum OS defends against, exactly how, and —
just as deliberately — what it does not. Every claim below corresponds to a
file in this repository; paths are given so you can verify rather than trust.

## Threat model

Sanctum OS is a **guest operating system in a virtual machine**. That framing
is the honest starting point, because it draws a hard line:

**In scope — what the hardening is for:**

- Network attackers: unsolicited inbound connections, protocol downgrade,
  DNS observation and tampering, local-network snooping and tracking.
- Hostile content inside the workspace: a malicious website, download, or
  compromised application trying to escape its sandbox, read other apps' data,
  escalate privileges, or attack the kernel.
- Theft of data at rest: someone who obtains the VM's disk file (or a backup
  of it) without the passphrase.
- Passive leakage: telemetry, connectivity phone-home, predictable hardware
  identifiers, secrets left in swap, core dumps, or logs.

**Out of scope — what no guest OS can defend against:**

- **A compromised host. The host always wins.** macOS (and VirtualBox itself)
  can read guest RAM — including LUKS master keys while the VM runs — capture
  the screen, log keystrokes, and modify the disk. Sanctum's encryption
  protects the VM's disk *file at rest*, not a live session on a hostile Mac.
  If your host is compromised, nothing in the guest matters.
- Hypervisor escape vulnerabilities in VirtualBox.
- Supply-chain compromise of Debian, Flathub, or Anthropic beyond what
  signature verification and key pinning can catch.
- A malicious local administrator: anyone with your `sudo` password is you.

Treat Sanctum as a strong compartment on a trustworthy host — not as
protection *from* the host.

## Hardening inventory

### Network

| Measure | Implementation |
| ------- | -------------- |
| Deny-all-inbound firewall | `config/includes.chroot/etc/nftables.conf` — input and forward chains `policy drop`; only loopback, established/related return traffic, rate-limited essential ICMP/ICMPv6 (path-MTU, NDP), and DHCPv6 client replies are accepted. Enabled at boot via `nftables.service` |
| Encrypted, validating DNS | `etc/systemd/resolved.conf.d/10-sanctum-dns.conf` — Quad9 (`9.9.9.9`, `149.112.112.112` + IPv6) with `DNSOverTLS=yes` and `DNSSEC=allow-downgrade`; no fallback resolvers. Quad9 is a Swiss nonprofit that does not log personal data and blocks known-malicious domains at the resolver |
| Name-leak protocols off | Same file: `LLMNR=no`, `MulticastDNS=no` — and `avahi-daemon` is masked outright |
| MAC randomization | `etc/NetworkManager/conf.d/10-sanctum.conf` — random MAC while scanning Wi-Fi, stable per-network random MAC for Wi-Fi connections, IPv6 privacy extensions (RFC 4941). A no-op inside a NAT VM; meaningful if the image ever runs on bare metal |
| No connectivity phone-home | Same file: NetworkManager captive-portal probing disabled |
| Zero listening services | Nothing in the image listens on the network. There is **no SSH server**, and `ssh`/`sshd`, `cups`, `rpcbind`, `ModemManager`, `wpa_supplicant`, `bluetooth`, and `avahi` units are masked (belt-and-braces — most are not even installed). See `config/hooks/normal/0600-services.hook.chroot` |

### System

| Measure | Implementation |
| ------- | -------------- |
| LUKS2 full-disk encryption | Pre-selected in the Calamares installer; `cryptsetup` + `cryptsetup-initramfs` from `config/package-lists/sanctum-installer.list.chroot`. Passphrase required at every boot; only the EFI partition is cleartext |
| AppArmor enforced | `apparmor`, `apparmor-profiles`, `apparmor-utils` installed; all shipped profiles forced to enforce mode in `config/hooks/normal/0700-security.hook.chroot` |
| Kernel lockdown + hardened cmdline | `etc/default/grub.d/10-sanctum.cfg` — `lockdown=integrity` (blocks kexec, `/dev/mem`, and other runtime kernel-modification paths), `init_on_alloc=1 init_on_free=1` (zeroed memory, blunts use-after-free), `slab_nomerge`, `page_alloc.shuffle=1`, `randomize_kstack_offset=on`. x86-only flags (`pti`, `vsyscall`) are intentionally absent; KPTI is always-on on arm64 |
| KSPP sysctls | `etc/sysctl.d/90-sanctum-hardening.conf`, quoted in full below |
| Kernel module blacklist | `etc/modprobe.d/10-sanctum-blacklist.conf` — legacy network protocols (DCCP, SCTP, RDS, TIPC, AX.25, …), rarely-used filesystems with historically buggy parsers (cramfs, hfs, udf, …), DMA-capable buses absent in VMs (FireWire, Thunderbolt), and Bluetooth. `install <mod> /bin/false` blocks loading even on request |
| zram-only swap | `etc/systemd/zram-generator.conf.d/10-sanctum.conf` — compressed swap in RAM (zstd, up to min(RAM/2, 4 GB)). No disk swap ever exists, so secrets cannot be paged to disk outside the LUKS envelope |
| No core dumps | Three layers: `kernel.core_pattern = |/bin/false` (sysctl), systemd-coredump `Storage=none` / `ProcessSizeMax=0`, and a hard `ulimit` of 0 — dumps can contain session tokens and keys |
| Root locked | `passwd -l root` at build time; administration is sudo-only through your user account |
| Private-by-default files | `umask 027`, `HOME_MODE`/`DIR_MODE` `0700` for all created users (`0700-security.hook.chroot`) |
| Bounded logs, PAM tmpdir | Journald capped (64 MB persistent / 32 MB runtime); `libpam-tmpdir` gives each user a private `/tmp` namespace path |
| cron/at restricted | `cron.allow`/`at.allow` contain only root (neither daemon is installed) |

### Applications and updates

| Measure | Implementation |
| ------- | -------------- |
| Sandboxed apps | Firefox and Telegram are Flathub Flatpaks running in bubblewrap sandboxes with portal-mediated file access — not loose debs with full home access |
| Tightened sandbox overrides | `config/hooks/normal/0300-flatpak-apps.hook.chroot` — both apps get `--nofilesystem=host --nofilesystem=home`; only `xdg-download` (Downloads) is reachable. Anything else goes through explicit file-picker portals |
| Firefox policy hardening | `config/includes.chroot/var/lib/flatpak/extension/org.mozilla.firefox.systemconfig/.../policies.json` — telemetry, studies, Pocket, sponsored content, search suggestions, and captive-portal probing disabled; HTTPS-Only mode on; tracking protection with cryptomining/fingerprinting blocking; tracker cookies rejected. Preferences are set, not locked — you stay in control |
| Automatic OS security updates | `etc/apt/apt.conf.d/20auto-upgrades` + `52sanctum-unattended-upgrades` — daily unattended-upgrades from Debian security/stable-updates **and** Anthropic's repository (`site=downloads.claude.ai`), so Claude Desktop patches itself too. No forced reboots |
| Automatic Flatpak updates | `sanctum-flatpak-update.timer` — daily, 10 minutes after boot, randomized. Firefox stays current without a software center |
| Pinned Anthropic signing key | `config/hooks/normal/0200-claude-repo.hook.chroot` — the key is fetched at **image build time** and its full fingerprint (`31DD DE24 DDFA B679 F42D 7BD2 BAA9 29FF 1A7E CACE`) is asserted; **the build fails on any mismatch**. The apt source is additionally constrained with `signed-by` and `arch=arm64`. The app itself is never redistributed — first boot installs it from Anthropic's repository over this key |

### The sysctl file, in full

`/etc/sysctl.d/90-sanctum-hardening.conf` (source:
`config/includes.chroot/etc/sysctl.d/90-sanctum-hardening.conf`):

```ini
# Sanctum OS — kernel hardening (KSPP-aligned, tuned for a desktop VM).
# Deliberately NOT disabled: unprivileged user namespaces — bubblewrap/Flatpak
# sandboxing (Firefox, Telegram) and Electron's chromium sandbox depend on them.

## Kernel information leaks
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.printk = 3 3 3 3

## Attack surface
kernel.kexec_load_disabled = 1
kernel.sysrq = 0
kernel.unprivileged_bpf_disabled = 1
net.core.bpf_jit_harden = 2
kernel.perf_event_paranoid = 3
kernel.io_uring_disabled = 2
vm.unprivileged_userfaultfd = 0
dev.tty.ldisc_autoload = 0
dev.tty.legacy_tiocsti = 0
kernel.warn_limit = 100
kernel.oops_limit = 100

## ptrace: only parent → child (debuggers still work on their own children)
kernel.yama.ptrace_scope = 1

## Filesystem hardening
fs.protected_symlinks = 1
fs.protected_hardlinks = 1
fs.protected_fifos = 2
fs.protected_regular = 2
fs.suid_dumpable = 0

## Core dumps off (may contain secrets)
kernel.core_pattern = |/bin/false

## Network hardening
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_rfc1337 = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1

## ASLR
vm.mmap_rnd_bits = 32
vm.mmap_rnd_compat_bits = 16
```

## What we deliberately did NOT do — and why

Honest hardening means naming the trade-offs, not hiding them.

- **Unprivileged user namespaces stay enabled.** Disabling them
  (`kernel.unprivileged_userns_clone=0` or the `user.max_user_namespaces`
  hammer) appears on many checklists. Sanctum's application security model *is*
  sandboxing: bubblewrap (Flatpak) and Chromium/Electron sandboxes — including
  Claude Desktop's — create user namespaces to build their containment.
  Disabling them would force those apps to run unsandboxed or with setuid
  helpers, a strictly worse posture. We mitigate the userns kernel attack
  surface instead: unprivileged BPF off, `io_uring` restricted, userfaultfd
  restricted, module blacklist, lockdown.

- **The root filesystem is mutable.** An immutable/image-based design (like
  OSTree systems) has real merit, but it would mean maintaining our own image
  update infrastructure and would break the promise that this is *Debian* —
  auditable, apt-driven, boring. The chosen posture is **hardened-mutable**:
  standard Debian stable underneath, with automatic security updates
  (unattended-upgrades daily, Flatpak daily) so the window between patch and
  deployment is hours, not "whenever the user remembers."

- **No SELinux.** Debian's mature MAC path is AppArmor; every shipped profile
  is enforced. Swapping in SELinux would trade a working, maintained
  configuration for an unmaintained bespoke one.

- **DNSSEC is `allow-downgrade`, not `yes`.** Strict DNSSEC breaks name
  resolution behind middleboxes and some captive setups with no user-visible
  explanation. Quad9 validates upstream regardless; DoT protects the path to
  Quad9.

- **The live session is soft.** The live user has passwordless sudo — that is
  how installers work, and nothing in a live session persists. All account
  hardening statements above describe the *installed* system.

- **macOS-host caveats.** Some protections end at the VM boundary, and you
  should know which: VirtualBox's clipboard sharing (once you enable Guest
  Additions) copies guest secrets into the host clipboard, which any Mac app
  can read. VM **snapshots capture RAM**, including disk-encryption keys — a
  snapshot of a running Sanctum VM on an unencrypted Mac disk undermines the
  guest's FDE. The `.vdi` file itself is only as private as your Mac: keep
  FileVault on. And Sanctum cannot patch VirtualBox — keep it current on the
  host.

## Reporting a vulnerability

Use GitHub's **private vulnerability reporting** on this repository (Security
tab ▸ Report a vulnerability) rather than a public issue, and include
reproduction steps against a named release or commit. Reports are acknowledged
as quickly as possible; fixes ship as a patched ISO release and, where the
component allows it, as a normal package update to installed systems. There is
no bug bounty — just credit, and our thanks.
