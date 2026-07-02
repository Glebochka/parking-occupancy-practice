from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from parking_occupancy.models import AVAILABLE_MODELS
from parking_occupancy.trainer import TrainConfig, train_and_evaluate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--models", nargs="*", default=AVAILABLE_MODELS)
    args = parser.parse_args()

    requested = args.models
    unknown = sorted(set(requested) - set(AVAILABLE_MODELS))
    if unknown:
        raise ValueError(f"Неизвестные модели: {unknown}")

    rows: list[dict[str, float | int | str]] = []
    for model_name in requested:
        print(f"\n=== {model_name} ===")
        config = TrainConfig(
            model_name=model_name,
            data_dir=args.data_dir,
            artifacts_dir=args.artifacts_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
            image_size=args.image_size,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            seed=args.seed,
        )
        metrics = train_and_evaluate(config)
        rows.append(metrics)

    summary = pd.DataFrame(rows).sort_values(by="f1", ascending=False)
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.artifacts_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print("\nSummary:")
    print(summary.to_string(index=False))
    print(f"\nSaved summary to: {summary_path}")


if __name__ == "__main__":
    main()
