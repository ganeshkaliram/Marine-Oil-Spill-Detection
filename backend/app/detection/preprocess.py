"""SAR preprocessing: loading, calibration, land-masking, tiling.

This maps raw Sentinel-1 dual-polarimetric GRD granules into normalized,
model-ready feature channels (VV, VH, and the VV/VH ratio used to separate oil
slicks from look-alikes).

For the scaffold we implement pure/standalone steps so the module can be tested
without rasterio if dependencies are absent; heavy raster IO is gated behind an
import that will be exercised once training data is downloaded.
"""

from __future__ import annotations

import numpy as np
from pathlib import Path

from app.config import settings


class SARPreprocessor:
    """Handles ingestion and normalization of raw SAR scenes."""

    def load_scene(self, scene_id: str):
        """Locate and read a scene from data/raw/sar.

        Returns
        -------
        tuple[np.ndarray, object, object]
            (multiband array [C,H,W], crs, affine transform).

        Raises
        ------
        FileNotFoundError
            If the scene does not exist on disk.
        """
        scene_root = settings.DATA_RAW_DIR / "sar" / scene_id
        if not scene_root.is_dir():
            # Accept either a directory or a single file.
            candidates = list((settings.DATA_RAW_DIR / "sar").glob(f"{scene_id}*"))
            if not candidates:
                raise FileNotFoundError(f"Scene {scene_id} not found")
            scene_root = candidates[0]

        # TODO(phase-1): load with rasterio, apply calibration (sigma0 dB),
        # land-mask, and return [VV, VH, VV/VH] channels.
        #
        # import rasterio
        # with rasterio.open(scene_granule) as src:
        #     vv = src.read(1); vh = src.read(2)
        #     crs = src.crs; transform = src.transform
        # array = np.stack([vv, vh, vv / (vh + 1e-6)])
        #
        raise NotImplementedError("Loading SAR scenes requires phase-1 dataset wiring.")

    @staticmethod
    def placeholder_mask(array: np.ndarray) -> np.ndarray:
        """Produce a zero mask (no slicks) as a runnable placeholder."""
        return np.zeros((array.shape[1], array.shape[2]), dtype=np.uint8)

    @staticmethod
    def denoise_lee(image: np.ndarray, window: int = 7) -> np.ndarray:
        """Apply a basic Lee speckle filter (wrapper for scipy-based impl).

        NOTE: pure-numpy stub for scaffold; production version uses scipy.ndimage
        convolution over the local mean/variance.
        """
        return image
