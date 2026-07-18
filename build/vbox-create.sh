#!/bin/sh
# Sanctum OS — create a correctly-configured VirtualBox ARM64 VM on the Mac host.
# VirtualBox 7.2+ on Apple Silicon: ARM64 guests only, UEFI-only, VMSVGA-only
# graphics, VirtIO storage. These settings encode all known-good choices.
set -eu

VM_NAME="Sanctum OS"
ISO="${1:-dist/$(ls dist 2>/dev/null | grep '\.iso$' | head -n1)}"
DISK_GB="${DISK_GB:-25}"
RAM_MB="${RAM_MB:-4096}"
CPUS="${CPUS:-4}"

[ -f "$ISO" ] || { echo "usage: $0 <path-to-sanctum-os.iso>" >&2; exit 1; }

VM_DIR="$HOME/VirtualBox VMs/$VM_NAME"

VBoxManage createvm --name "$VM_NAME" --platform-architecture arm \
    --ostype Debian_arm64 --register

VBoxManage modifyvm "$VM_NAME" \
    --memory "$RAM_MB" \
    --cpus "$CPUS" \
    --graphicscontroller vmsvga \
    --vram 128 \
    --usb-xhci on \
    --audio-driver none \
    --nic1 nat \
    --clipboard-mode bidirectional

VBoxManage createmedium disk --filename "$VM_DIR/$VM_NAME.vdi" \
    --size $((DISK_GB * 1024)) --format VDI

VBoxManage storagectl "$VM_NAME" --name "VirtIO" --add virtio-scsi
VBoxManage storageattach "$VM_NAME" --storagectl "VirtIO" --port 0 \
    --device 0 --type hdd --medium "$VM_DIR/$VM_NAME.vdi"
VBoxManage storageattach "$VM_NAME" --storagectl "VirtIO" --port 1 \
    --device 0 --type dvddrive --medium "$ISO"

echo ""
echo "VM '$VM_NAME' created. Start it with:"
echo "  VBoxManage startvm \"$VM_NAME\""
