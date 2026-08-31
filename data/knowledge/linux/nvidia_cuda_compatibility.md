# NVIDIA Driver / CUDA Compatibility Reference (Linux)

Linux GPU diagnosis reference for NVIDIA driver branches, CUDA toolkit
compatibility rules, and upgrade guidance. Maintained as a document — when
NVIDIA ships a new branch, update this file; no code change is needed.

## Driver / CUDA Matrix

| Driver branch | Matched CUDA | Branch type | Notes |
|---------------|--------------|-------------|-------|
| 575.x | 12.8+ | Development/beta | Newest features, less field testing |
| 565.x | 12.7 | Production | Latest production branch |
| 560.x | 12.6 | Production | Stable, widely tested |
| 555.x | 12.5 | Production | |
| 550.x | 12.4 | LTS | Very stable, widely deployed |
| 545.x | 12.3 | Production | |
| 535.x | 12.2 | LTS | Previous LTS |
| 525.x | 12.0 | Production | |
| 520.x | 11.8 | Production | |
| 515.x | 11.7 | Production | |

## Compatibility Rules

- A driver ALWAYS supports its matched CUDA version AND all older CUDA
  versions. Example: driver 575.x supports CUDA 12.8, 12.7, 12.6, 12.5,
  12.4, 12.3, 12.2, 12.0, 11.8, 11.7, and older.
- CUDA is COMPATIBLE when the installed version is the driver's matched
  version or older.
- If the installed CUDA version is NEWER than what the driver supports,
  the combination is INCOMPATIBLE — a high-priority issue.
- If CUDA is not installed but ML frameworks need it, recommend installing
  the toolkit matched to the driver (not newer).
- For Ampere and newer GPUs (RTX 30xx, A-series, RTX 40xx, RTX 50xx):
  driver 550 or newer is recommended.

## Role-Specific Constraints

- **Display GPUs** (driving a monitor) need desktop compatibility — check
  Wayland/X11 and compositor (GNOME/KDE) support before upgrading drivers.
- **Compute-only GPUs** have no display-server constraints; any driver
  branch that matches the required CUDA version is fine.
- In multi-GPU systems, consider which GPU drives the display and which is
  dedicated to compute before recommending a driver change.

## Known Good Combinations

| Driver | CUDA | Note |
|---------|------|-------|
| 565.57 | 12.7 | Latest production |
| 550.127 | 12.4 | LTS, very stable |
| 535.183 | 12.2 | Previous LTS |

## ML Framework Checks

- **PyTorch**: `python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
  — the CUDA available flag must be true and the bundled CUDA version must
  be equal to or older than the driver's matched CUDA version.
- **TensorFlow**: `python3 -c "import tensorflow as tf; print(tf.__version__, tf.config.list_physical_devices('GPU'))"`
  — GPU devices must be listed.
- A framework reports no GPU when its bundled CUDA is newer than the
  driver supports — fix the driver/CUDA pairing, not the framework.

## Upgrade Guidance

- Only recommend an upgrade when a SPECIFIC newer version provides a clear
  benefit (a fix, a needed CUDA bump) — never upgrade for its own sake.
- On secure-boot systems, signed drivers (or enrolled MOK keys) are
  required; an unsigned driver will fail to load.
- Jumping between major branches (e.g. 550 LTS to 575 beta) carries
  moderate risk on display GPUs; LTS-to-LTS moves are the safest.