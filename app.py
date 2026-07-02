from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import torch
from PIL import Image

from predict import load_checkpoint
from parking_occupancy.trainer import build_eval_transform


ROOT = Path(__file__).resolve().parent
ARTIFACTS_DIR = ROOT / "artifacts"
MANIFEST_PATH = ROOT / "data" / "processed" / "manifest.csv"
SUMMARY_PATH = ARTIFACTS_DIR / "summary.csv"
WORKBOOK_PATH = ARTIFACTS_DIR / "parking_occupancy_results.xlsx"
HISTORY_PATH = ARTIFACTS_DIR / "prediction_history.jsonl"


@st.cache_data
def load_summary() -> pd.DataFrame:
    return pd.read_csv(SUMMARY_PATH).sort_values("f1", ascending=False).reset_index(drop=True)


@st.cache_data
def load_manifest() -> pd.DataFrame:
    return pd.read_csv(MANIFEST_PATH)


@st.cache_resource
def load_model_bundle(model_name: str):
    checkpoint_path = ARTIFACTS_DIR / model_name / "best.pt"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, image_size, idx_to_class, model_name = load_checkpoint(checkpoint_path, device)
    transform = build_eval_transform(image_size)
    return model, transform, idx_to_class, device, model_name


def run_prediction(model_name: str, image: Image.Image) -> dict[str, object]:
    model, transform, idx_to_class, device, loaded_model_name = load_model_bundle(model_name)
    tensor = transform(image.convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        probs = torch.softmax(model(tensor), dim=1).squeeze(0).cpu()
        pred_idx = int(torch.argmax(probs).item())
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model_name": loaded_model_name,
        "prediction": idx_to_class[pred_idx],
        "confidence": float(probs[pred_idx].item()),
        "probabilities": {
            idx_to_class[idx]: float(probs[idx].item()) for idx in range(len(idx_to_class))
        },
    }


def append_history(result: dict[str, object], image_name: str) -> None:
    payload = {**result, "image_name": image_name}
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_history() -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return pd.DataFrame()
    with HISTORY_PATH.open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return pd.DataFrame(rows)


def main() -> None:
    st.set_page_config(page_title="Parking Occupancy Demo", page_icon="🚗", layout="wide")
    st.title("Демонстрационный модуль определения занятости парковочного места")
    st.caption("Практика по теме компьютерного зрения: классификация парковочного места как свободного или занятого.")

    summary_df = load_summary()
    manifest_df = load_manifest()
    best_model = summary_df.iloc[0]["model_name"]

    with st.sidebar:
        st.header("Параметры")
        selected_model = st.selectbox("Модель", summary_df["model_name"].tolist(), index=0)
        st.metric("Лучшая модель по F1", best_model)
        st.metric("Лучшая F1", f"{summary_df.iloc[0]['f1']:.4f}")
        if WORKBOOK_PATH.exists():
            with WORKBOOK_PATH.open("rb") as fh:
                st.download_button(
                    "Скачать Excel-отчет",
                    fh.read(),
                    file_name="parking_occupancy_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    col1, col2 = st.columns([1.2, 1.0])
    with col1:
        st.subheader("Изображение")
        upload = st.file_uploader("Загрузите изображение парковочного места", type=["jpg", "jpeg", "png"])

        sample_options = ["Не использовать"] + [
            f"{row.label} | {row.weather} | {Path(row.path).name}"
            for row in manifest_df[manifest_df["split"] == "test"].head(20).itertuples()
        ]
        sample_choice = st.selectbox("Или выберите тестовый пример", sample_options, index=0)

        image = None
        image_name = "uploaded_image"
        if upload is not None:
            image = Image.open(upload).convert("RGB")
            image_name = upload.name
        elif sample_choice != "Не использовать":
            selected_name = sample_choice.split(" | ", 2)[-1]
            row = manifest_df[manifest_df["path"].str.endswith(selected_name)].iloc[0]
            image = Image.open(row["path"]).convert("RGB")
            image_name = selected_name

        if image is not None:
            st.image(image, caption=image_name, use_container_width=True)

        predict_now = st.button("Определить состояние места", type="primary", disabled=image is None)

    with col2:
        st.subheader("Результат")
        if predict_now and image is not None:
            result = run_prediction(selected_model, image)
            append_history(result, image_name)
            st.success(f"Состояние: {result['prediction']}")
            st.metric("Уверенность", f"{result['confidence']:.3f}")
            probs_df = pd.DataFrame(
                {
                    "class": list(result["probabilities"].keys()),
                    "probability": list(result["probabilities"].values()),
                }
            ).set_index("class")
            st.bar_chart(probs_df)
            st.json(result)
        else:
            st.info("Загрузите изображение или выберите пример из тестовой выборки.")

        st.subheader("Краткая статистика")
        st.dataframe(summary_df[["model_name", "accuracy", "precision", "recall", "f1"]], use_container_width=True)

    st.subheader("История проверок")
    history_df = load_history()
    if history_df.empty:
        st.info("История пока пуста.")
    else:
        st.dataframe(history_df.sort_values("timestamp", ascending=False), use_container_width=True)
        stats_col1, stats_col2, stats_col3 = st.columns(3)
        stats_col1.metric("Всего проверок", str(len(history_df)))
        stats_col2.metric("Определено как occupied", str((history_df["prediction"] == "occupied").sum()))
        stats_col3.metric("Определено как empty", str((history_df["prediction"] == "empty").sum()))


if __name__ == "__main__":
    main()
