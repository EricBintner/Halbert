#!/bin/bash
# Build the `aec` feature for arm64 on this machine.
#
# The default toolchain drifts to x86_64: this Mac's Homebrew prefix is
# Intel (/usr/local), and somewhere in the cargo -> build-script -> meson
# chain the universal python/clang binaries end up on their x86_64 slices,
# so meson detects an x86_64 host and enables x86-only SSE2 sources while
# rustc links arm64. The overrides below fix all of it:
#   - a meson wrapper forces the interpreter under `arch -arm64`, so meson
#     detects an aarch64 host and skips the SSE2 sources;
#   - CC/CXX pin the clang slice to arm64;
#   - PKG_CONFIG_LIBDIR hides the Intel-brew abseil so meson builds its own
#     arm64 subproject instead of linking x86_64 archives.
# Only needed for `--features aec` (bundled C++) builds; plain cargo builds
# with the feature off need none of this.
set -e
cd "$(dirname "$0")"

# Force-arm64 meson: runs the same module entry the meson launcher uses.
WRAP_DIR="target/meson-arm64-wrapper"
mkdir -p "$WRAP_DIR"
printf '#!/bin/sh\nexec arch -arm64 %s -m mesonbuild.mesonmain "$@"\n' \
  /Applications/Xcode.app/Contents/Developer/usr/bin/python3 \
  > "$WRAP_DIR/meson"
chmod +x "$WRAP_DIR/meson"

export PATH="$PWD/$WRAP_DIR:$HOME/Library/Python/3.9/bin:$PATH"
export PKG_CONFIG_LIBDIR=/var/empty
export CC="clang -arch arm64"
export CXX="clang++ -arch arm64"
export CFLAGS="-arch arm64"
export CXXFLAGS="-arch arm64"
export LDFLAGS="-arch arm64"
cargo build --features aec