"""Phase 1: Slick detection service.

This module coordinates the SAR ingestion -> preprocessing -> model -> geometry
characterization flow. The machine-learning model itself lives in
``app.models.unet``; here we handle orchestration and geometry post-processing.

The design is intentionally DI-based so the heavy model can be mocked in tests
and swapped for lighter inference backends later.
"""

from __future__ import annotations

from typing import Sequence

from app.config import settings
from app.core.schemas import SlickDetection
from app.core.utils import gen_id, utcnow
from app.detection.preprocess import SARPreprocessor


class DetectionService:
    """High-level orchestrator for the detection stage."""

    def __init__(self, preprocessor: SARPreprocessor | None = None) -> None:
        self.preprocessor = preprocessor or SARPreprocessor()
        self._store: dict[str, SlickDetection] = {}

    def list_all(self) -> list[SlickDetection]:
        return list(self._store.values())

    def get(self, slick_id: str) -> SlickDetection | None:
        return self._store.get(slick_id)

    def run_detection(self, scene_id: str) -> list[SlickDetection]:
        """Run the full detection chain for a scene id and cache the results.

        Raises
        ------
        NotImplementedError
            When the trained detection model weights are not present yet. This
            keeps the pipeline runnable (empty result) while training is pending.
        """
        try:
            # Load raw multiband raster for the scene.
            array, crs, transform = self.preprocessor.load_scene(scene_id)
        except FileNotFoundError:
            raise

        # Placeholder for model inference. Training connects here once the UNet
        # weights are shipped (scripts/train_detector.py).
        if not settings.DETECTION_MODEL_WEIGHTS.is_file():
            raise NotImplementedError(
                "Detection model weights not found. Train Phase 1 first: "
                "`python scripts/train_detector.py`."
            )

        # TODO(phase-1): run UNet, threshold -> binary mask -> labelled blobs.
        mask = self.preprocessor.placeholder_mask(array)

        slicks = self._mask_to_slicks(scene_id, mask, crs, transform)
        for s in slicks:
            self._store[s.id] = s
        return slicks

    def _mask_to_slicks(
        self,
        scene_id: str,
        mask,
        crs,
        transform,
    ) -> list[SlickDetection]:
        """Convert a segmentation mask into characterized SlickDetections."""
        # TODO(phase-1): connected components over mask, compute geometry.
        # For the scaffold we return an empty list until connected components
        # are wired to the geometry extraction.
        return []
