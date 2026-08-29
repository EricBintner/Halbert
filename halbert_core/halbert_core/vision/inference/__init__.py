# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Local computer vision inference modules.

All modules use lazy imports for heavy dependencies (ultralytics, onnxruntime,
mediapipe) so the core vision package loads without them. Install the
`cv-inference` optional dependency group to enable:

    pip install halbert-core[cv-inference]

Modules:
  detector.py — YOLOv8 ONNX object detection (person, car, dog, etc.)
  face.py     — Face detection via OpenCV DNN or MediaPipe
"""
