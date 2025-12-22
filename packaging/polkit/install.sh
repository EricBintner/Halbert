#!/bin/bash
# Install Halbert PolicyKit configuration for privileged operations
# This enables GUI password prompts when accessing protected files or running privileged commands

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Halbert PolicyKit configuration..."

# Install the policy file
echo "  Installing policy file to /usr/share/polkit-1/actions/"
sudo cp "$SCRIPT_DIR/com.halbert.editor.policy" /usr/share/polkit-1/actions/

# Install the file helper script
echo "  Installing file helper to /usr/local/bin/"
sudo cp "$SCRIPT_DIR/halbert-file-helper" /usr/local/bin/
sudo chmod +x /usr/local/bin/halbert-file-helper

# Install the exec helper script
echo "  Installing exec helper to /usr/local/bin/"
sudo cp "$SCRIPT_DIR/halbert-exec-helper" /usr/local/bin/
sudo chmod +x /usr/local/bin/halbert-exec-helper

echo ""
echo "✓ PolicyKit configuration installed successfully!"
echo ""
echo "You can now:"
echo "  - Edit system configuration files in Halbert"
echo "  - Run privileged commands from the dashboard"
echo ""
echo "A password dialog will appear when elevated privileges are needed."
