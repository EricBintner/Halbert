.PHONY: help dev dev-web build install-units uninstall-units install-configs show-config-dir

help:
	@echo "Development:"
	@echo "  dev                - Start Tauri desktop app + backend (full development)"
	@echo "  dev-web            - Start backend only (browser at http://localhost:8000)"
	@echo "  build              - Build Tauri production app"
	@echo ""
	@echo "Installation:"
	@echo "  install-units      - Copy systemd units to /etc/systemd/system and enable"
	@echo "  uninstall-units    - Disable and remove systemd units"
	@echo "  install-configs    - Create /etc/cerebric and copy example configs if missing"
	@echo "  show-config-dir    - Print resolved config_dir from Cerebric"

# ─────────────────────────────────────────────────────────────────────────────
# Development
# ─────────────────────────────────────────────────────────────────────────────

dev:
	@./scripts/dev-dashboard.sh

dev-web:
	@./scripts/dev-dashboard-web.sh

build:
	@echo "Building Cerebric Tauri app..."
	cd cerebric_core/cerebric_core/dashboard/frontend && npm run build && npm run tauri build

install-units:
	@echo "Installing Cerebric systemd units (requires sudo)"
	sudo cp packaging/systemd/system/*.service /etc/systemd/system/
	sudo cp packaging/systemd/system/*.path /etc/systemd/system/ || true
	sudo systemctl daemon-reload
	sudo systemctl enable --now cerebric-ingest-journald.service
	sudo systemctl enable --now cerebric-ingest-hwmon.service
	sudo systemctl enable --now cerebric-config-watch.service
	sudo systemctl enable --now cerebric-config-watch.path || true
	@echo ""
	@echo "Dashboard service available but not auto-started:"
	@echo "  sudo systemctl enable --now cerebric-dashboard@$(USER).service"

uninstall-units:
	@echo "Uninstalling Cerebric systemd units (requires sudo)"
	sudo systemctl disable --now cerebric-config-watch.path || true
	sudo systemctl disable --now cerebric-config-watch.service || true
	sudo systemctl disable --now cerebric-ingest-hwmon.service || true
	sudo systemctl disable --now cerebric-ingest-journald.service || true
	sudo rm -f /etc/systemd/system/cerebric-*.service /etc/systemd/system/cerebric-*.path
	sudo systemctl daemon-reload

install-configs:
	@echo "Installing example configs to /etc/cerebric (requires sudo); existing files preserved"
	sudo mkdir -p /etc/cerebric
	@if [ ! -f /etc/cerebric/ingestion.yml ]; then sudo cp config/ingestion.yml /etc/cerebric/; fi
	@if [ ! -f /etc/cerebric/config-registry.yml ]; then sudo cp config/config-registry.yml /etc/cerebric/; fi
	@if [ ! -f /etc/cerebric/policy.yml ]; then sudo cp config/policy.yml /etc/cerebric/; fi

show-config-dir:
	@python3 -c 'import os,sys; sys.path.insert(0,"cerebric_core"); from cerebric_core.cerebric_core.utils.paths import config_dir; print(config_dir())'
