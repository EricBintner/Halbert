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
	@echo "  install-configs    - Create /etc/halbert and copy example configs if missing"
	@echo "  show-config-dir    - Print resolved config_dir from Halbert"

# ─────────────────────────────────────────────────────────────────────────────
# Development (Tauri + FastAPI)
# ─────────────────────────────────────────────────────────────────────────────

dev:
	@./scripts/dev-dashboard.sh

dev-web:
	@./scripts/dev-dashboard-web.sh

build:
	@echo "Building Halbert Tauri app..."
	cd halbert_core/halbert_core/dashboard/frontend && npm run build && npm run tauri build

install-units:
	@echo "Installing Halbert systemd units (requires sudo)"
	sudo cp packaging/systemd/system/*.service /etc/systemd/system/
	sudo cp packaging/systemd/system/*.path /etc/systemd/system/ || true
	sudo systemctl daemon-reload
	sudo systemctl enable --now halbert-ingest-journald.service
	sudo systemctl enable --now halbert-ingest-hwmon.service
	sudo systemctl enable --now halbert-config-watch.service
	sudo systemctl enable --now halbert-config-watch.path || true
	@echo ""
	@echo "Dashboard service available but not auto-started:"
	@echo "  sudo systemctl enable --now halbert-dashboard@$(USER).service"

uninstall-units:
	@echo "Uninstalling Halbert systemd units (requires sudo)"
	sudo systemctl disable --now halbert-config-watch.path || true
	sudo systemctl disable --now halbert-config-watch.service || true
	sudo systemctl disable --now halbert-ingest-hwmon.service || true
	sudo systemctl disable --now halbert-ingest-journald.service || true
	sudo rm -f /etc/systemd/system/halbert-*.service /etc/systemd/system/halbert-*.path
	sudo systemctl daemon-reload

install-configs:
	@echo "Installing example configs to /etc/halbert (requires sudo); existing files preserved"
	sudo mkdir -p /etc/halbert
	@if [ ! -f /etc/halbert/ingestion.yml ]; then sudo cp config/ingestion.yml /etc/halbert/; fi
	@if [ ! -f /etc/halbert/config-registry.yml ]; then sudo cp config/config-registry.yml /etc/halbert/; fi
	@if [ ! -f /etc/halbert/policy.yml ]; then sudo cp config/policy.yml /etc/halbert/; fi

show-config-dir:
	@python3 -c 'import os,sys; sys.path.insert(0,"halbert_core"); from halbert_core.halbert_core.utils.paths import config_dir; print(config_dir())'
