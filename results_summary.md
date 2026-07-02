# Results Summary

## Dataset

- Source: `PKLot`
- Total cropped samples: `10000`
- Classes: `empty`, `occupied`
- Split:
  - `train`: `7000`
  - `val`: `1500`
  - `test`: `1500`

## Training setup

- Epochs: `2`
- Batch size: `32`
- Image size: `224`
- Device: `cuda`

## Model comparison

| Model | Accuracy | Precision | Recall | F1 | Latency ms/image | Size MB |
|---|---:|---:|---:|---:|---:|---:|
| EfficientNet-B0 | 0.9700 | 0.9468 | 0.9960 | 0.9708 | 10.8661 | 15.582 |
| MobileNetV3 Small | 0.9693 | 0.9444 | 0.9973 | 0.9702 | 10.3347 | 5.925 |
| ResNet18 | 0.9693 | 0.9467 | 0.9947 | 0.9701 | 12.2642 | 42.714 |
| DenseNet121 | 0.9687 | 0.9466 | 0.9933 | 0.9694 | 11.8195 | 27.111 |
| ConvNeXt-Tiny | 0.9680 | 0.9488 | 0.9893 | 0.9687 | 12.8220 | 106.194 |

## Best model

- Best model by F1-score: `EfficientNet-B0`
- Test metrics:
  - Accuracy: `0.9700`
  - Precision: `0.9468`
  - Recall: `0.9960`
  - F1-score: `0.9708`
- Confusion matrix: `[[708, 42], [3, 747]]`

## Weather robustness

| Weather | Samples | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| cloudy | 514 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| rainy | 200 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| sunny | 786 | 0.9427 | 0.9052 | 0.9926 | 0.9469 |

## Deliverables

- `artifacts/parking_occupancy_results.xlsx`
- `report_assets/weather_comparison.png`
- `report_assets/source_comparison.png`
- `report_assets/training_pipeline.png`
- `report_assets/streamlit_demo.png`

## Report assets

- `report_assets/dataset_distribution.png`
- `report_assets/dataset_samples.png`
- `report_assets/model_comparison.png`
- `report_assets/best_model_confusion_matrix.png`
- `report_assets/prediction_examples.png`
