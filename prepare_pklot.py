from __future__ import annotations

import argparse
import io
import random
import tarfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw
from sklearn.model_selection import train_test_split


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-per-class", type=int, default=6000)
    parser.add_argument("--test-size", type=float, default=0.15)
    parser.add_argument("--val-size", type=float, default=0.15)
    parser.add_argument("--padding", type=float, default=0.08)
    parser.add_argument("--jpeg-quality", type=int, default=88)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def extract_metadata(member_name: str) -> dict[str, str]:
    parts = Path(member_name).parts
    if len(parts) < 5:
        return {"scene": "unknown", "weather": "unknown", "date": "unknown"}
    return {
        "scene": parts[1],
        "weather": parts[2],
        "date": parts[3],
    }


def parse_points(space: ET.Element) -> list[tuple[int, int]]:
    contour = space.find("contour")
    if contour is None:
        return []

    points: list[tuple[int, int]] = []
    for point in contour:
        x = int(float(point.attrib["x"]))
        y = int(float(point.attrib["y"]))
        points.append((x, y))
    return points


def crop_space(image: Image.Image, points: list[tuple[int, int]], padding: float) -> Image.Image:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width = max_x - min_x
    height = max_y - min_y
    pad_x = max(2, int(width * padding))
    pad_y = max(2, int(height * padding))

    left = max(0, min_x - pad_x)
    top = max(0, min_y - pad_y)
    right = min(image.width, max_x + pad_x)
    bottom = min(image.height, max_y + pad_y)

    cropped = image.crop((left, top, right, bottom))
    local_points = [(x - left, y - top) for x, y in points]

    mask = Image.new("L", cropped.size, 0)
    drawer = ImageDraw.Draw(mask)
    drawer.polygon(local_points, fill=255)

    background = Image.new("RGB", cropped.size, (0, 0, 0))
    return Image.composite(cropped, background, mask)


def reservoir_update(
    bucket: list[dict[str, object]],
    seen_count: int,
    limit: int,
    candidate: dict[str, object],
    rng: random.Random,
) -> None:
    if len(bucket) < limit:
        bucket.append(candidate)
        return

    replacement_index = rng.randrange(seen_count)
    if replacement_index < limit:
        bucket[replacement_index] = candidate


def select_candidates(archive_path: Path, max_per_class: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    selected = {"empty": [], "occupied": []}
    seen = {"empty": 0, "occupied": 0}

    with tarfile.open(archive_path, "r|gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.lower().endswith(".xml"):
                continue

            file_obj = tar.extractfile(member)
            if file_obj is None:
                continue

            root = ET.fromstring(file_obj.read())
            metadata = extract_metadata(member.name)
            image_member = str(Path(member.name).with_suffix(".jpg")).replace("\\", "/")
            frame_name = Path(member.name).stem
            source = root.attrib.get("id", metadata["scene"])

            for space in root.findall("space"):
                points = parse_points(space)
                if len(points) < 3:
                    continue

                label = "occupied" if space.attrib.get("occupied") == "1" else "empty"
                seen[label] += 1
                candidate = {
                    "image_member": image_member,
                    "label": label,
                    "source": source,
                    "scene": metadata["scene"],
                    "weather": metadata["weather"],
                    "date": metadata["date"],
                    "frame": frame_name,
                    "space_id": space.attrib.get("id", "unknown"),
                    "points": points,
                }
                reservoir_update(selected[label], seen[label], max_per_class, candidate, rng)

    records = selected["empty"] + selected["occupied"]
    if not records:
        raise RuntimeError("No XML candidates were selected from PKLot archive.")

    rng.shuffle(records)
    return records


def materialize_selected_samples(
    archive_path: Path,
    output_dir: Path,
    records: list[dict[str, object]],
    padding: float,
    jpeg_quality: int,
) -> pd.DataFrame:
    temp_dir = output_dir / "_all"
    for label in ("empty", "occupied"):
        (temp_dir / label).mkdir(parents=True, exist_ok=True)

    records_by_image: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        records_by_image[str(record["image_member"])].append(record)

    saved_index = 0
    materialized: list[dict[str, object]] = []

    with tarfile.open(archive_path, "r|gz") as tar:
        for member in tar:
            if not member.isfile() or member.name not in records_by_image:
                continue

            file_obj = tar.extractfile(member)
            if file_obj is None:
                continue

            image = Image.open(io.BytesIO(file_obj.read())).convert("RGB")
            for record in records_by_image[member.name]:
                points = record["points"]
                cropped = crop_space(image, points, padding=padding)
                saved_index += 1

                label = str(record["label"])
                file_name = (
                    f"{saved_index:07d}_{record['source']}_{record['weather']}_{record['date']}_"
                    f"{record['frame']}_space{record['space_id']}_{label}.jpg"
                )
                save_path = temp_dir / label / file_name
                cropped.save(save_path, quality=jpeg_quality)

                materialized.append(
                    {
                        "path": str(save_path.resolve()),
                        "label": label,
                        "source": record["source"],
                        "scene": record["scene"],
                        "weather": record["weather"],
                        "date": record["date"],
                        "frame": record["frame"],
                        "space_id": record["space_id"],
                    }
                )

    if len(materialized) != len(records):
        raise RuntimeError(
            f"Expected {len(records)} cropped samples, but created {len(materialized)}."
        )
    return pd.DataFrame(materialized)


def split_dataset(df: pd.DataFrame, test_size: float, val_size: float, seed: int) -> pd.DataFrame:
    train_df, test_df = train_test_split(
        df,
        test_size=test_size,
        random_state=seed,
        stratify=df["label"],
    )
    val_ratio = val_size / (1.0 - test_size)
    train_df, val_df = train_test_split(
        train_df,
        test_size=val_ratio,
        random_state=seed,
        stratify=train_df["label"],
    )

    train_df = train_df.copy()
    val_df = val_df.copy()
    test_df = test_df.copy()
    train_df["split"] = "train"
    val_df["split"] = "val"
    test_df["split"] = "test"
    return pd.concat([train_df, val_df, test_df], ignore_index=True)


def finalize_structure(df: pd.DataFrame, output_dir: Path) -> None:
    for split in ("train", "val", "test"):
        for label in ("empty", "occupied"):
            (output_dir / split / label).mkdir(parents=True, exist_ok=True)

    for idx, row in df.reset_index(drop=True).iterrows():
        source_path = Path(row["path"])
        target_path = output_dir / row["split"] / row["label"] / f"{idx:07d}_{source_path.name}"
        source_path.replace(target_path)
        df.at[row.name, "path"] = str(target_path.resolve())

    temp_dir = output_dir / "_all"
    if temp_dir.exists():
        for child in temp_dir.iterdir():
            if child.is_dir():
                for nested in child.iterdir():
                    if nested.is_file():
                        break
                else:
                    child.rmdir()
        if not any(temp_dir.iterdir()):
            temp_dir.rmdir()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    selected_records = select_candidates(
        archive_path=args.archive_path,
        max_per_class=args.max_per_class,
        seed=args.seed,
    )
    materialized_df = materialize_selected_samples(
        archive_path=args.archive_path,
        output_dir=args.output_dir,
        records=selected_records,
        padding=args.padding,
        jpeg_quality=args.jpeg_quality,
    )
    split_df = split_dataset(
        materialized_df,
        test_size=args.test_size,
        val_size=args.val_size,
        seed=args.seed,
    )
    finalize_structure(split_df, args.output_dir)

    manifest_path = args.output_dir / "manifest.csv"
    split_df.to_csv(manifest_path, index=False)

    summary = split_df.groupby(["split", "label"]).size().reset_index(name="count")
    print(summary.to_string(index=False))
    print(f"\nTotal samples: {len(split_df)}")
    print(f"Manifest saved to: {manifest_path}")


if __name__ == "__main__":
    main()
