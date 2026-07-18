# Sanctum OS — convenience targets
.PHONY: iso assets clean vm-create vm-destroy

# Build the ISO locally (requires Docker/OrbStack + ~20 GB free disk)
iso:
	./build/container-build.sh

# Rasterize branding assets only (requires librsvg: brew install librsvg)
assets:
	./build/mkassets.sh

clean:
	rm -rf dist build.log

# Create a VirtualBox ARM64 VM wired for Sanctum OS (run on the Mac host)
vm-create:
	./build/vbox-create.sh

vm-destroy:
	VBoxManage unregistervm "Sanctum OS" --delete 2>/dev/null || true
