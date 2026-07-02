from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import torch
from PIL import Image


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from parking_occupancy.models import build_model
from parking_occupancy.trainer import build_eval_transform


def load_checkpoint(checkpoint_path: Path, device: torch.device):
    payload = torch.load(checkpoint_path, map_location=device)
    model_name = payload["model_name"]
    image_size = payload.get("image_size", 224)
    class_to_idx = payload["class_to_idx"]
    idx_to_class = {idx: name for name, idx in class_to_idx.items()}

    model = build_model(model_name=model_name, num_classes=len(class_to_idx), pretrained=False)
    model.load_state_dict(payload["state_dict"])
    model.to(device)
    model.eval()
    return model, image_size, idx_to_class, model_name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--history-path", type=Path, default=ROOT / "artifacts" / "prediction_history.jsonl")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, image_size, idx_to_class, model_name = load_checkpoint(args.checkpoint, device)
    transform = build_eval_transform(image_size)

    image = Image.open(args.image).convert("RGB")
    tensor = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1).squeeze(0).cpu()
        pred_idx = int(torch.argmax(probs).item())

    prediction = idx_to_class[pred_idx]
    confidence = float(probs[pred_idx].item())
    probabilities = {idx_to_class[i]: float(probs[i].item()) for i in range(len(idx_to_class))}

    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_name": model_name,
        "image": str(args.image.resolve()),
        "prediction": prediction,
        "confidence": confidence,
        "probabilities": probabilities,
    }

    args.history_path.parent.mkdir(parents=True, exist_ok=True)
    with args.history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
