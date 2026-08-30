"""Detection model definition (DeepLabV3+ / UNet with resnet backbone).

This module wraps the segmentation architecture that discriminates oil slicks
from look-alikes. It uses the `segmentation-models-pytorch` library as the
model source, which provides DeepLabV3+ with a ResNet backbone out of the box.

The `build_detector` factory is the single function used by both the training
script and the detection service, so the architecture stays in one place.
"""

from __future__ import annotations

import torch
import torch.nn as nn


def build_detector(
    n_channels: int = 3,
    n_classes: int = 1,
    backbone: str = "resnet34",
    pretrained: bool = True,
) -> nn.Module:
    """Build the segmentation model.

    Parameters
    ----------
    n_channels : int
        Number of input channels (3 for VV, VH, VV/VH).
    n_classes : int
        Number of output classes (1 for binary slick/background).
    backbone : str
        SMP encoder backbone name.
    pretrained : bool
        Load ImageNet-pretrained encoder weights.

    Returns
    -------
    nn.Module
        A DeepLabV3+ model ready for training or inference.
    """
    try:
        import segmentation_models_pytorch as smp
    except ImportError as exc:  # pragma: no cover - deps not installed in scaffold
        raise ImportError(
            "segmentation-models-pytorch is required. "
            "Install with: pip install -r requirements.txt"
        ) from exc

    model = smp.DeepLabV3Plus(
        encoder_name=backbone,
        encoder_weights="imagenet" if pretrained else None,
        in_channels=n_channels,
        classes=n_classes,
    )
    return model


class ContrastiveProjectionHead(nn.Module):
    """Small MLP head used for supervised contrastive pre-training.

    During representation learning the encoder is tuned so embeddings of same-
    class patches (spills / look-alikes) are pulled together while different
    classes are pushed apart. This reduces the false-positive rate from look-
    alike dark patches.
    """

    def __init__(self, in_dim: int = 512, out_dim: int = 128) -> None:
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(in_dim, in_dim),
            nn.ReLU(inplace=True),
            nn.Linear(in_dim, out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x)
