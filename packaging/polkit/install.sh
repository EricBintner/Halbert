#!/bin/bash
# Install Halbert PolicyKit configuration for privileged file editing
# This enables GUI password prompts when editing system config files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Halbert PolicyKit configuration..."

# Install the policy file
echo "  Installing policy file to /usr/share/polkit-1/actions/"
sudo cp "$SCRIPT_DIR/com.halbert.editor.policy" /usr/share/polkit-1/actions/

# Install the helper script
echo "  Installing helper script to /usr/local/bin/"
sudo cp "$SCRIPT_DIR/halbert-file-helper" /usr/local/bin/
sudo chmod +x /usr/local/bin/halbert-file-helper

echo ""
echo "✓ PolicyKit configuration installed successfully!"
echo ""
echo "You can now edit system configuration files in Halbert."
echo "A password dialog will appear when accessing protected files."
