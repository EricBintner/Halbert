"""
AppImage Documentation Scraper.

Phase 26: Universal App Management

Generates AppImage documentation and troubleshooting guides.
"""

import logging
import json
from typing import List
from datetime import datetime
from pathlib import Path
import hashlib

from .base import BaseScraper, ScrapedDocument, ScraperConfig

logger = logging.getLogger('halbert')


class AppImageDocsScraper(BaseScraper):
    """Scraper for AppImage documentation and troubleshooting guides."""
    
    def __init__(self, config: ScraperConfig):
        super().__init__(config)
    
    def get_source_name(self) -> str:
        return "appimage-docs"
    
    def scrape(self) -> List[ScrapedDocument]:
        documents = []
        logger.info("Generating AppImage documentation...")
        documents.extend(self._generate_guides())
        logger.info(f"Total AppImage documents: {len(documents)}")
        return documents
    
    def _generate_guides(self) -> List[ScrapedDocument]:
        documents = []
        
        guides = [
            {
                "title": "AppImage Quick Start Guide",
                "content": self._quick_start(),
                "tags": ["appimage", "portable", "basics"],
                "category": "getting_started",
            },
            {
                "title": "AppImage Troubleshooting Guide",
                "content": self._troubleshooting(),
                "tags": ["appimage", "troubleshooting", "errors"],
                "category": "troubleshooting",
            },
            {
                "title": "AppImage Desktop Integration",
                "content": self._integration_guide(),
                "tags": ["appimage", "desktop", "integration", "launcher"],
                "category": "configuration",
            },
            {
                "title": "AppImage Security and Verification",
                "content": self._security_guide(),
                "tags": ["appimage", "security", "signatures"],
                "category": "security",
            },
        ]
        
        for guide in guides:
            doc_id = f"appimage-guide-{hashlib.md5(guide['title'].encode()).hexdigest()[:12]}"
            
            documents.append(ScrapedDocument(
                id=doc_id,
                url=f"synthetic://halbert/appimage/{doc_id}",
                title=guide["title"],
                content=guide["content"],
                source="halbert-appimage-guides",
                category=guide["category"],
                tags=["linux", "package-manager"] + guide["tags"],
                scraped_at=datetime.utcnow().isoformat(),
                metadata={"platform": "linux", "doc_type": "guide", "synthetic": True}
            ))
        
        return documents
    
    def _quick_start(self) -> str:
        return """# AppImage Quick Start Guide

AppImage is a portable application format - one file per app, runs on any Linux.

## What is AppImage?

- Single executable file containing app + dependencies
- No installation needed
- Works on any Linux distribution
- Just download, make executable, and run

## Running an AppImage

### 1. Download the AppImage
Download from the app's website or AppImageHub (https://appimage.github.io/)

### 2. Make it Executable
```bash
chmod +x Application.AppImage
```

### 3. Run it
```bash
./Application.AppImage
```

Or double-click in your file manager.

## Recommended Location

Store AppImages in a consistent location:
```bash
mkdir -p ~/Applications
mv ~/Downloads/Application.AppImage ~/Applications/
```

## Command-Line Options

Most AppImages support these flags:
```bash
# Show help
./Application.AppImage --help

# Show version
./Application.AppImage --version

# Extract contents (don't run)
./Application.AppImage --appimage-extract

# Get desktop integration info
./Application.AppImage --appimage-help
```

## Desktop Integration

To add AppImage to your application menu:
1. Use AppImageLauncher (recommended)
2. Or create a .desktop file manually

## Updating AppImages

AppImages don't auto-update. To update:
1. Download new version
2. Replace old file
3. Or use AppImageUpdate tool

## Removing AppImages

Just delete the file:
```bash
rm ~/Applications/Application.AppImage
```

Also remove desktop entry if created:
```bash
rm ~/.local/share/applications/appimagekit-*.desktop
```
"""

    def _troubleshooting(self) -> str:
        return """# AppImage Troubleshooting Guide

## Common Issues

### "Permission denied" Error

**Cause**: File not marked as executable

**Solution**:
```bash
chmod +x Application.AppImage
```

### "FUSE not found" or "fusermount" Error

**Cause**: FUSE (Filesystem in Userspace) not installed

**Solution**:
```bash
# Ubuntu/Debian
sudo apt install fuse libfuse2

# Fedora
sudo dnf install fuse fuse-libs

# Arch
sudo pacman -S fuse2
```

### "cannot execute binary file"

**Cause**: Wrong architecture (e.g., running x86_64 on ARM)

**Solution**:
```bash
# Check your architecture
uname -m

# Check AppImage architecture
file Application.AppImage
```
Download the correct architecture version.

### AppImage Starts but Crashes

**Solutions**:
1. Run from terminal to see error:
   ```bash
   ./Application.AppImage
   ```

2. Try extracting and running:
   ```bash
   ./Application.AppImage --appimage-extract
   ./squashfs-root/AppRun
   ```

3. Check for missing libraries:
   ```bash
   ./Application.AppImage --appimage-extract
   ldd ./squashfs-root/usr/bin/application 2>&1 | grep "not found"
   ```

### Sandbox Errors (Firejail, etc.)

**Cause**: AppImage sandboxed incorrectly

**Solution**:
```bash
# Run without sandbox
APPIMAGE_EXTRACT_AND_RUN=1 ./Application.AppImage

# Or extract first
./Application.AppImage --appimage-extract
./squashfs-root/AppRun
```

### Graphics/OpenGL Issues

**Cause**: GPU driver incompatibility

**Solutions**:
```bash
# Try with software rendering
LIBGL_ALWAYS_SOFTWARE=1 ./Application.AppImage

# Or try different driver
__GLX_VENDOR_LIBRARY_NAME=mesa ./Application.AppImage
```

### Qt/GTK Theme Issues

**Cause**: AppImage bundles old toolkit version

**Solutions**:
```bash
# For Qt apps
QT_STYLE_OVERRIDE=fusion ./Application.AppImage

# For GTK apps - usually harder to fix
# Try extracting and modifying
```

### "Exec format error"

**Causes**:
1. Corrupted download
2. Wrong architecture
3. Not actually an AppImage

**Solutions**:
```bash
# Verify file type
file Application.AppImage

# Re-download
# Check SHA256 if provided
sha256sum Application.AppImage
```

### AppImage Works but Won't Open Files

**Cause**: File associations not set up

**Solution**:
1. Right-click file → Open With → Choose AppImage
2. Or set in ~/.config/mimeapps.list

### Slow Startup

**Cause**: Large AppImage, FUSE overhead

**Solutions**:
1. Extract and run directly:
   ```bash
   ./Application.AppImage --appimage-extract
   ./squashfs-root/AppRun
   ```

2. Use faster storage (SSD vs HDD)

## Debugging

### Extract and Inspect
```bash
./Application.AppImage --appimage-extract
ls squashfs-root/
cat squashfs-root/AppRun
```

### Check Dependencies
```bash
./Application.AppImage --appimage-extract
ldd squashfs-root/usr/bin/* 2>&1 | grep -v "linux-vdso"
```

### Environment Variables
```bash
# Useful debug variables
APPIMAGE_EXTRACT_AND_RUN=1  # Extract to temp, run from there
APPIMAGE_DEBUG_OUTPUT=1     # Show debug output
```
"""

    def _integration_guide(self) -> str:
        return """# AppImage Desktop Integration

## AppImageLauncher (Recommended)

AppImageLauncher automatically integrates AppImages into your desktop.

### Installation

**Ubuntu/Debian**:
```bash
sudo add-apt-repository ppa:appimagelauncher-team/stable
sudo apt update
sudo apt install appimagelauncher
```

**Fedora**:
```bash
# Download from GitHub releases
# https://github.com/TheAssassin/AppImageLauncher/releases
```

**Arch**:
```bash
yay -S appimagelauncher
```

### Features

- Auto-prompt when running AppImages
- Creates menu entries automatically
- Moves AppImages to central location
- Handles updates
- Removes menu entries when deleting AppImage

## Manual Desktop Integration

### Create .desktop File

```bash
# Create desktop entry
cat > ~/.local/share/applications/myapp.desktop << EOF
[Desktop Entry]
Type=Application
Name=My Application
Exec=/home/username/Applications/MyApp.AppImage
Icon=/home/username/Applications/myapp.png
Categories=Utility;
Terminal=false
EOF

# Update desktop database
update-desktop-database ~/.local/share/applications
```

### Extract Icon from AppImage

```bash
./Application.AppImage --appimage-extract
cp squashfs-root/*.png ~/Applications/app-icon.png
rm -rf squashfs-root
```

### Add to PATH

For CLI AppImages:
```bash
# Create symlink
ln -s ~/Applications/MyApp.AppImage ~/.local/bin/myapp

# Make sure ~/.local/bin is in PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

## appimaged Daemon

Alternative to AppImageLauncher - monitors directories for AppImages.

```bash
# Download appimaged
wget https://github.com/probonopd/go-appimage/releases/download/continuous/appimaged-*-x86_64.AppImage

# Run as daemon
./appimaged-*-x86_64.AppImage
```

## File Associations

### Register MIME Type

```bash
# Create MIME type file
cat > ~/.local/share/mime/packages/appimage.xml << EOF
<?xml version="1.0"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-appimage">
    <comment>AppImage Application</comment>
    <glob pattern="*.AppImage"/>
    <glob pattern="*.appimage"/>
  </mime-type>
</mime-info>
EOF

# Update MIME database
update-mime-database ~/.local/share/mime
```

## Recommended Folder Structure

```
~/Applications/
├── firefox.AppImage
├── vlc.AppImage
├── gimp.AppImage
└── icons/
    ├── firefox.png
    ├── vlc.png
    └── gimp.png
```
"""

    def _security_guide(self) -> str:
        return """# AppImage Security and Verification

## Security Considerations

### Download Sources

✅ **Safe sources**:
- Official project websites
- GitHub releases pages
- AppImageHub (https://appimage.github.io/)

⚠️ **Be cautious**:
- Random download sites
- Unverified forum links
- Modified/repacked AppImages

### Verify Downloads

#### Check SHA256/MD5
```bash
# If hash provided by developer
sha256sum Application.AppImage
# Compare with published hash
```

#### GPG Signatures
```bash
# If .asc signature provided
gpg --verify Application.AppImage.asc Application.AppImage
```

## AppImage Signing

### Embedded Signatures

Some AppImages contain embedded signatures:
```bash
# Check for signature
./Application.AppImage --appimage-signature

# Verify if gpg key available
./Application.AppImage --appimage-verify
```

### Check Certificate Info
```bash
./Application.AppImage --appimage-extract
cat squashfs-root/.sig  # If exists
```

## Sandboxing AppImages

AppImages run with full user permissions by default.

### Using Firejail
```bash
# Install Firejail
sudo apt install firejail

# Run AppImage in sandbox
firejail ./Application.AppImage

# With custom profile
firejail --profile=myprofile ./Application.AppImage
```

### Using Bubblewrap
```bash
# Basic sandbox
bwrap --ro-bind / / --dev /dev --proc /proc \
  --unshare-all --share-net \
  ./Application.AppImage
```

## Inspecting AppImages

### View Contents
```bash
./Application.AppImage --appimage-extract
ls -la squashfs-root/

# Check AppRun script
cat squashfs-root/AppRun

# Look for suspicious scripts
find squashfs-root -name "*.sh" -exec cat {} \;
```

### Check Libraries
```bash
./Application.AppImage --appimage-extract
find squashfs-root -name "*.so*" | head -20
```

## Best Practices

1. **Download from official sources only**
2. **Verify checksums when available**
3. **Keep AppImages in dedicated folder**
4. **Use sandboxing for untrusted apps**
5. **Don't run AppImages as root**
6. **Check update mechanisms** - some phone home

## Malware Scanning

```bash
# ClamAV scan
clamscan Application.AppImage

# Extract and scan contents
./Application.AppImage --appimage-extract
clamscan -r squashfs-root/
```
"""


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate AppImage documentation")
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    config = ScraperConfig(output_dir=args.output_dir)
    scraper = AppImageDocsScraper(config)
    documents = scraper.scrape()
    
    output_file = args.output_dir / "appimage_docs.jsonl"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        for doc in documents:
            f.write(json.dumps(doc.to_dict()) + '\n')
    
    print(f"Saved {len(documents)} documents to {output_file}")


if __name__ == '__main__':
    main()
