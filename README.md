# Parking Occupancy Project

Проект для практики по теме `Определение занятости парковочного места`.

## Что уже заложено

- подготовка датасета `PKLot` в формат `ImageFolder`
- обучение 5 архитектур:
  - `resnet18`
  - `mobilenet_v3_small`
  - `efficientnet_b0`
  - `densenet121`
  - `convnext_tiny`
- автоматическое сохранение метрик
- сводная таблица результатов
- предсказание по одному изображению
- лог истории предсказаний в `JSONL`
- экспорт итоговых результатов в `Excel`
- анализ устойчивости по погодным условиям
- демонстрационный интерфейс на `Streamlit`

## Структура

```text
parking_occupancy_project/
  data/
    raw/
    processed/
  artifacts/
  src/
    parking_occupancy/
  prepare_pklot.py
  benchmark.py
  predict.py
  export_results_bundle.py
  app.py
```

## Датасет

Используемая база: `PKLot`.

Почему она подходит:

- задача ровно совпадает с темой практики
- есть два класса: `empty` и `occupied`
- есть разные погодные условия
- датасет часто используется как базовый бенчмарк для парковочных мест

Перед началом работы:

1. Скачай `PKLot.tar.gz` в папку `data/raw`.
2. Запусти подготовку датасета.
3. Запусти обучение и сравнение моделей.

## Установка зависимостей

```powershell
pip install -r requirements.txt
```

Если `torch` и `torchvision` уже установлены, дополнительно ставить их не нужно.

## Подготовка датасета

```powershell
python prepare_pklot.py --archive-path data/raw/PKLot.tar.gz --output-dir data/processed --max-per-class 5000
```

Скрипт:

- читает `PKLot.tar.gz` последовательно
- вырезает парковочные места по XML-разметке
- формирует сбалансированную выборку `empty/occupied`
- разбивает данные на `train/val/test`
- создает структуру для `torchvision.datasets.ImageFolder`
- сохраняет `manifest.csv`

## Обучение и сравнение моделей

```powershell
python benchmark.py --data-dir data/processed --epochs 5 --batch-size 32
```

После запуска будут созданы:

- `artifacts/<model_name>/best.pt`
- `artifacts/<model_name>/metrics.json`
- `artifacts/summary.csv`

## Материалы для отчета

```powershell
python generate_report_assets.py --data-dir data/processed --artifacts-dir artifacts --output-dir report_assets
```

Будут сохранены:

- `report_assets/dataset_distribution.png`
- `report_assets/dataset_samples.png`
- `report_assets/model_comparison.png`
- `report_assets/best_model_confusion_matrix.png`
- `report_assets/prediction_examples.png`

## Предсказание по одному изображению

```powershell
python predict.py --checkpoint artifacts/resnet18/best.pt --image path\\to\\image.jpg
```

Результат:

- вывод класса и вероятности
- запись истории в `artifacts/prediction_history.jsonl`

## Excel-отчет и погодный анализ

```powershell
python export_results_bundle.py
```

Будут созданы:

- `artifacts/parking_occupancy_results.xlsx`
- `artifacts/weather_metrics.csv`
- `artifacts/source_metrics.csv`
- `report_assets/weather_comparison.png`
- `report_assets/source_comparison.png`
- `report_assets/training_pipeline.png`

## Streamlit-демо

```powershell
streamlit run app.py
```

Возможности интерфейса:

- загрузка изображения парковочного места
- предсказание класса и уверенности
- просмотр вероятностей классов
- просмотр краткой статистики по моделям
- история проверок
- скачивание итогового `Excel`-отчета

## Реальный порядок работы для практики

1. Подготовить `PKLot`.
2. Прогнать быстрый тест на 1-2 эпохи.
3. Убедиться, что пайплайн работает.
4. Обучить 5 моделей на нормальном числе эпох.
5. Сравнить `accuracy`, `precision`, `recall`, `f1`, скорость инференса и размер моделей.
6. Выбрать лучшую модель.
7. На основе результатов заполнять дневник и отчет.
