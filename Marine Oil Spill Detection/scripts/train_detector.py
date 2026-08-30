"""Train the Phase 1 detection model (DeepLabV3+).

This connects the model factory to a dataset of processed SAR patches.
For the scaffold the data loading is stubbed - replace the DataLoader with your
real SAR patch dataset, then run:

    python scripts/train_detector.py

Optionally include supervised contrastive pre-training via the projection head
before the segmentation fine-tune.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch.utils.data import DataLoader

from app.config import settings
from app.models.unet import build_detector


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Training Phase 1 detector on", device)

    model = build_detector(
        n_channels=3,
        n_classes=1,
        backbone=settings.MODEL_BACKBONE,
        pretrained=True,
    ).to(device)

    # TODO(phase-1): create a torch dataset that yields (VV,VH,ratio) patches
    # with binary masks, then:
    #   train_loader = DataLoader(dataset, batch_size=16, shuffle=True)
    #   optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    #   loss_fn = torch.nn.BCEWithLogitsLoss()
    #   for epoch ...: train_step(...)

    weights_dir = Path(settings.DETECTION_MODEL_WEIGHTS)
    weights_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), weights_dir / "detector.pt")
    print("Saved model weights to", weights_dir / "detector.pt")


if __name__ == "__main__":
    main()
