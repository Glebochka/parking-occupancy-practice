from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from torch import nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from tqdm import tqdm

from parking_occupancy.models import build_model


IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


@dataclass
class TrainConfig:
    model_name: str
    data_dir: Path
    artifacts_dir: Path
    epochs: int = 5
    batch_size: int = 32
    num_workers: int = 4
    image_size: int = 224
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    seed: int = 42


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_train_transform(image_size: int):
    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def build_eval_transform(image_size: int):
    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def build_loaders(data_dir: Path, image_size: int, batch_size: int, num_workers: int):
    train_ds = datasets.ImageFolder(data_dir / "train", transform=build_train_transform(image_size))
    val_ds = datasets.ImageFolder(data_dir / "val", transform=build_eval_transform(image_size))
    test_ds = datasets.ImageFolder(data_dir / "test", transform=build_eval_transform(image_size))

    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True,
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True,
    )
    return train_ds, train_loader, val_loader, test_loader


def run_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    total_count = 0

    for images, labels in tqdm(loader, leave=False):
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()

        batch_size = images.size(0)
        total_loss += loss.item() * batch_size
        total_count += batch_size

    return total_loss / max(total_count, 1)


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []
    total_images = 0
    started = time.perf_counter()

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        logits = model(images)
        preds = torch.argmax(logits, dim=1).cpu().tolist()
        y_pred.extend(preds)
        y_true.extend(labels.tolist())
        total_images += images.size(0)

    elapsed = time.perf_counter() - started
    cm = confusion_matrix(y_true, y_pred)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average="binary", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="binary", zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average="binary", zero_division=0)),
        "confusion_matrix": cm.tolist(),
        "latency_ms_per_image": float((elapsed / max(total_images, 1)) * 1000.0),
    }


def save_checkpoint(model, model_name: str, class_to_idx: dict[str, int], image_size: int, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_name": model_name,
            "class_to_idx": class_to_idx,
            "image_size": image_size,
            "state_dict": model.state_dict(),
        },
        path,
    )


def train_and_evaluate(config: TrainConfig) -> dict[str, float | int | str]:
    set_seed(config.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_ds, train_loader, val_loader, test_loader = build_loaders(
        data_dir=config.data_dir,
        image_size=config.image_size,
        batch_size=config.batch_size,
        num_workers=config.num_workers,
    )

    model = build_model(config.model_name, num_classes=len(train_ds.classes), pretrained=True).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)

    model_dir = config.artifacts_dir / config.model_name
    best_path = model_dir / "best.pt"
    best_f1 = -1.0

    for epoch in range(1, config.epochs + 1):
        train_loss = run_epoch(model, train_loader, criterion, optimizer, device)
        val_metrics = evaluate(model, val_loader, device)
        scheduler.step()

        print(
            f"epoch={epoch} "
            f"train_loss={train_loss:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} "
            f"val_f1={val_metrics['f1']:.4f}"
        )

        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            save_checkpoint(
                model=model,
                model_name=config.model_name,
                class_to_idx=train_ds.class_to_idx,
                image_size=config.image_size,
                path=best_path,
            )

    payload = torch.load(best_path, map_location=device)
    model.load_state_dict(payload["state_dict"])
    test_metrics = evaluate(model, test_loader, device)
    model_size_mb = best_path.stat().st_size / (1024 * 1024)

    result = {
        "model_name": config.model_name,
        "accuracy": round(test_metrics["accuracy"], 6),
        "precision": round(test_metrics["precision"], 6),
        "recall": round(test_metrics["recall"], 6),
        "f1": round(test_metrics["f1"], 6),
        "latency_ms_per_image": round(test_metrics["latency_ms_per_image"], 6),
        "model_size_mb": round(model_size_mb, 3),
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "image_size": config.image_size,
        "device": str(device),
        "train_samples": len(train_ds),
        "val_samples": len(val_loader.dataset),
        "test_samples": len(test_loader.dataset),
        "confusion_matrix": test_metrics["confusion_matrix"],
    }

    model_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = model_dir / "metrics.json"
    with metrics_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    return result
