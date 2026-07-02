from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--output-dir", type=Path, default=Path("report_assets"))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def save_distribution_plot(manifest: pd.DataFrame, output_dir: Path) -> None:
    summary = manifest.groupby(["split", "label"]).size().unstack(fill_value=0)
    ax = summary.plot(kind="bar", figsize=(8, 5), color=["#4C78A8", "#F58518"])
    ax.set_title("PKLot Subset Distribution")
    ax.set_xlabel("Split")
    ax.set_ylabel("Images")
    ax.legend(title="Class")
    plt.tight_layout()
    plt.savefig(output_dir / "dataset_distribution.png", dpi=180)
    plt.close()


def save_sample_grid(manifest: pd.DataFrame, output_dir: Path, seed: int) -> None:
    random.seed(seed)
    rows = []
    for label in ("empty", "occupied"):
        subset = manifest[manifest["label"] == label].sample(n=min(6, (manifest["label"] == label).sum()), random_state=seed)
        rows.extend(subset.to_dict("records"))

    images = [Image.open(row["path"]).convert("RGB").resize((180, 120)) for row in rows]
    cols = 3
    tile_w, tile_h = 180, 120
    label_h = 24
    canvas = Image.new("RGB", (cols * tile_w, math.ceil(len(images) / cols) * (tile_h + label_h)), "white")
    draw = ImageDraw.Draw(canvas)

    for idx, (row, image) in enumerate(zip(rows, images)):
        x = (idx % cols) * tile_w
        y = (idx // cols) * (tile_h + label_h)
        canvas.paste(image, (x, y))
        draw.text((x + 4, y + tile_h + 4), f"{row['label']} | {row['weather']}", fill="black")

    canvas.save(output_dir / "dataset_samples.png")


def save_model_comparison(artifacts_dir: Path, output_dir: Path) -> None:
    summary_path = artifacts_dir / "summary.csv"
    if not summary_path.exists():
        return

    summary = pd.read_csv(summary_path).sort_values("f1", ascending=False)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].bar(summary["model_name"], summary["f1"], color="#54A24B")
    axes[0].set_title("Model Comparison by F1")
    axes[0].set_ylabel("F1-score")
    axes[0].tick_params(axis="x", rotation=30)

    axes[1].bar(summary["model_name"], summary["latency_ms_per_image"], color="#E45756")
    axes[1].set_title("Inference Latency")
    axes[1].set_ylabel("ms per image")
    axes[1].tick_params(axis="x", rotation=30)

    plt.tight_layout()
    plt.savefig(output_dir / "model_comparison.png", dpi=180)
    plt.close()

    best_model = summary.iloc[0]["model_name"]
    metrics_path = artifacts_dir / best_model / "metrics.json"
    if not metrics_path.exists():
        return

    with metrics_path.open("r", encoding="utf-8") as fh:
        metrics = json.load(fh)
    cm = metrics["confusion_matrix"]

    fig, ax = plt.subplots(figsize=(4.5, 4))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_title(f"Confusion Matrix: {best_model}")
    ax.set_xticks([0, 1], labels=["empty", "occupied"])
    ax.set_yticks([0, 1], labels=["empty", "occupied"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i][j]), ha="center", va="center", color="black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.savefig(output_dir / "best_model_confusion_matrix.png", dpi=180)
    plt.close()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = args.data_dir / "manifest.csv"
    if manifest_path.exists():
        manifest = pd.read_csv(manifest_path)
        save_distribution_plot(manifest, args.output_dir)
        save_sample_grid(manifest, args.output_dir, args.seed)

    save_model_comparison(args.artifacts_dir, args.output_dir)


if __name__ == "__main__":
    main()
