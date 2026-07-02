from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import torch
from PIL import Image
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

from predict import load_checkpoint
from parking_occupancy.trainer import build_eval_transform


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
ASSETS_DIR = ROOT / "report_assets"
MANIFEST_PATH = ROOT / "data" / "processed" / "manifest.csv"
SUMMARY_PATH = ARTIFACTS_DIR / "summary.csv"
WORKBOOK_PATH = ARTIFACTS_DIR / "parking_occupancy_results.xlsx"


def compute_metrics(df: pd.DataFrame) -> dict[str, float | int]:
    y_true = (df["label"] == "occupied").astype(int)
    y_pred = (df["prediction"] == "occupied").astype(int)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    return {
        "samples": int(len(df)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "tn": int(cm[0][0]),
        "fp": int(cm[0][1]),
        "fn": int(cm[1][0]),
        "tp": int(cm[1][1]),
    }


def predict_subset(model_name: str, checkpoint_path: Path, subset_df: pd.DataFrame) -> pd.DataFrame:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, image_size, idx_to_class, _ = load_checkpoint(checkpoint_path, device)
    transform = build_eval_transform(image_size)

    rows: list[dict[str, object]] = []
    for _, row in subset_df.iterrows():
        image = Image.open(row["path"]).convert("RGB")
        tensor = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            probs = torch.softmax(model(tensor), dim=1).squeeze(0).cpu()
            pred_idx = int(torch.argmax(probs).item())
        rows.append(
            {
                **row.to_dict(),
                "model_name": model_name,
                "prediction": idx_to_class[pred_idx],
                "confidence_empty": float(probs[0].item()),
                "confidence_occupied": float(probs[1].item()),
                "confidence": float(probs[pred_idx].item()),
            }
        )
    return pd.DataFrame(rows)


def save_weather_plot(weather_df: pd.DataFrame) -> None:
    order = ["sunny", "cloudy", "rainy"]
    plot_df = weather_df.set_index("weather").reindex(order).reset_index()
    x = range(len(plot_df))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([v - width / 2 for v in x], plot_df["accuracy"], width=width, label="Accuracy", color="#4C78A8")
    ax.bar([v + width / 2 for v in x], plot_df["f1"], width=width, label="F1-score", color="#F58518")
    ax.set_xticks(list(x), plot_df["weather"])
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("Metric value")
    ax.set_title("Best Model Stability by Weather")
    ax.legend()
    plt.tight_layout()
    plt.savefig(ASSETS_DIR / "weather_comparison.png", dpi=180)
    plt.close()


def save_source_plot(source_df: pd.DataFrame) -> None:
    plot_df = source_df.sort_values("accuracy", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(plot_df["source"], plot_df["accuracy"], color="#54A24B")
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("Accuracy")
    ax.set_title("Best Model Accuracy by Parking Lot Source")
    plt.tight_layout()
    plt.savefig(ASSETS_DIR / "source_comparison.png", dpi=180)
    plt.close()


def save_pipeline_diagram() -> None:
    fig, ax = plt.subplots(figsize=(12, 2.8))
    ax.axis("off")
    blocks = [
        ("PKLot.tar.gz", 0.05, "#4C78A8"),
        ("XML parsing\nand crop selection", 0.27, "#72B7B2"),
        ("Balanced dataset\n10 000 images", 0.49, "#54A24B"),
        ("Training 5 models", 0.71, "#F58518"),
        ("Demo module\nand Excel report", 0.89, "#E45756"),
    ]
    for idx, (label, xpos, color) in enumerate(blocks):
        rect = plt.Rectangle((xpos - 0.09, 0.35), 0.18, 0.3, color=color, alpha=0.9)
        ax.add_patch(rect)
        ax.text(xpos, 0.5, label, ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        if idx < len(blocks) - 1:
            ax.annotate("", xy=(xpos + 0.11, 0.5), xytext=(xpos + 0.02, 0.5), arrowprops=dict(arrowstyle="->", lw=2))
    plt.tight_layout()
    plt.savefig(ASSETS_DIR / "training_pipeline.png", dpi=180)
    plt.close()


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    summary_df = pd.read_csv(SUMMARY_PATH).sort_values("f1", ascending=False).reset_index(drop=True)
    manifest_df = pd.read_csv(MANIFEST_PATH)
    split_df = (
        manifest_df.groupby(["split", "label"]).size().reset_index(name="count").sort_values(["split", "label"])
    )

    training_df = pd.DataFrame(
        [
            {
                "parameter": "epochs",
                "value": 2,
            },
            {
                "parameter": "batch_size",
                "value": 32,
            },
            {
                "parameter": "image_size",
                "value": 224,
            },
            {
                "parameter": "optimizer",
                "value": "AdamW",
            },
            {
                "parameter": "learning_rate",
                "value": 3e-4,
            },
            {
                "parameter": "weight_decay",
                "value": 1e-4,
            },
            {
                "parameter": "scheduler",
                "value": "CosineAnnealingLR",
            },
            {
                "parameter": "device",
                "value": "cuda" if torch.cuda.is_available() else "cpu",
            },
        ]
    )

    best_model_name = summary_df.iloc[0]["model_name"]
    checkpoint_path = ARTIFACTS_DIR / best_model_name / "best.pt"
    test_df = manifest_df[manifest_df["split"] == "test"].copy()
    predictions_df = predict_subset(best_model_name, checkpoint_path, test_df)

    weather_rows = []
    for weather, group in predictions_df.groupby("weather"):
        weather_rows.append({"weather": weather, **compute_metrics(group)})
    weather_df = pd.DataFrame(weather_rows).sort_values("weather").reset_index(drop=True)

    source_rows = []
    for source, group in predictions_df.groupby("source"):
        source_rows.append({"source": source, **compute_metrics(group)})
    source_df = pd.DataFrame(source_rows).sort_values("source").reset_index(drop=True)

    overall_df = pd.DataFrame([{"scope": "test_all", **compute_metrics(predictions_df)}])

    history_path = ARTIFACTS_DIR / "prediction_history.jsonl"
    history_df = pd.DataFrame()
    if history_path.exists():
        with history_path.open("r", encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        history_df = pd.DataFrame(rows)

    with pd.ExcelWriter(WORKBOOK_PATH, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="model_summary", index=False)
        split_df.to_excel(writer, sheet_name="split_distribution", index=False)
        training_df.to_excel(writer, sheet_name="training_config", index=False)
        overall_df.to_excel(writer, sheet_name="overall_test_metrics", index=False)
        weather_df.to_excel(writer, sheet_name="weather_metrics", index=False)
        source_df.to_excel(writer, sheet_name="source_metrics", index=False)
        predictions_df.head(500).to_excel(writer, sheet_name="prediction_examples", index=False)
        if not history_df.empty:
            history_df.to_excel(writer, sheet_name="history", index=False)

    weather_df.to_csv(ARTIFACTS_DIR / "weather_metrics.csv", index=False)
    source_df.to_csv(ARTIFACTS_DIR / "source_metrics.csv", index=False)

    save_weather_plot(weather_df)
    save_source_plot(source_df)
    save_pipeline_diagram()

    print(f"Workbook saved to: {WORKBOOK_PATH}")


if __name__ == "__main__":
    main()
