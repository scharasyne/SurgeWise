"""Reproduce the archive's evaluation forest and export origin-specific QC forecasts."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory, NamedTemporaryFile
from zipfile import ZipFile

import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_HASH = "0848d84bdc4f1da46a91ef3b3aca8ef3e5824ec6e275d68c01857bbb956b1c1b"
PREFIX = "SurgeWise_80_10_10/"
MEMBERS = ("evaluate_split.py", "engine.py", "data/processed/gp_cases.csv", "data/raw/annual_cases.csv",
           "data/processed/population_geometry.csv", "data/processed/adjacency.csv", "data/raw/upri_2023.csv")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "production/SurgeWise_80_10_10.zip")
    parser.add_argument("--output", type=Path, default=ROOT / "data/processed/qc-archive-rf-replay.npz")
    parser.add_argument("--validation-output", type=Path,
                        default=ROOT / "apps/web/public/data/qc-archive-forecast-validation.json")
    args = parser.parse_args()
    raw = args.archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_HASH or sklearn.__version__ != "1.8.0":
        raise ValueError("Use the reviewed training archive and scikit-learn==1.8.0.")
    with ZipFile(io.BytesIO(raw)) as archive, TemporaryDirectory() as folder:
        for member in MEMBERS:
            path = Path(folder, member)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(PREFIX + member))
        sys.path[:0] = [folder, str(ROOT)]
        # The reviewed top-level training scripts import the existing app's feature builder.
        import engine
        import evaluate_split
        with threadpool_limits(limits=1):
            models, columns = evaluate_split.fit_candidates({"RF": "RF_shallow"}, evaluate_split.TRAIN_END)
            model = models["RF"].set_params(n_jobs=1)
            rows = []
            for origin in range(evaluate_split.TRAIN_END, len(engine.city_cases) - 1):
                inputs, _, _ = engine.design(origin, "safe", engine.city_cases[:origin + 1])
                rows.append(model.predict(inputs[columns].to_numpy()).reshape(6, 142))
        counts = np.round(np.array(rows), decimals=10)
        if counts.shape != (104, 6, 142) or not np.isfinite(counts).all() or counts.min() < 0:
            raise ValueError("Invalid historical origin/horizon/area coverage")
        with archive.open(PREFIX + "outputs/evaluation/weekly_backtest.csv") as stream:
            all_rows = pd.read_csv(stream)
            backtest = all_rows.query('protocol == "chronological" and method == "RF_shallow"')
        matched = counts[backtest.origin - evaluate_split.TRAIN_END, backtest.horizon - 1, :].sum(axis=1)
        if len(backtest) != 104 or not np.allclose(matched, backtest.pred_city, rtol=0, atol=1e-7):
            raise ValueError("Reproduced local forecasts differ from archived evaluation totals")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=args.output.parent, delete=False) as staged:
            np.savez_compressed(staged, cases=counts, codes=engine.codes.astype(str), archive_sha256=ARCHIVE_HASH,
                                last_training_year=2020, first_target_year=2021)
        Path(staged.name).chmod(0o644)
        Path(staged.name).replace(args.output)
        validation = []
        for protocol in ("chronological", "random_blocked"):
            test = all_rows.query("split == 'test' and protocol == @protocol")
            rf = test.query("method == 'RF_shallow'").set_index(["origin", "horizon"]).sort_index()
            baseline = test.query("method == 'city_persist_seasonal_share'").set_index(["origin", "horizon"]).sort_index()
            if len(rf) != 52 or not rf.actual_city.equals(baseline.actual_city):
                raise ValueError("Holdout forecasts must share the same 52 observed targets")
            error = (rf.pred_city - rf.actual_city).abs()
            validation.append({"protocol": protocol, "weeks": len(rf), "cityMae": float(error.mean()),
                               "cityWapePercent": float(100 * error.sum() / rf.actual_city.sum()),
                               "persistenceMae": float((baseline.pred_city - baseline.actual_city).abs().mean()),
                               "byHorizon": [{"weeksAhead": h, "n": len(group), "cityMae": float(group.mean())}
                                             for h, group in error.groupby(level="horizon")]})
        report = {"model": "RF_shallow", "geography": "QUEZON_CITY", "trainingThrough": 2020,
                  "units": "reported QC cases per morbidity week", "archiveSha256": ARCHIVE_HASH,
                  "source": "outputs/evaluation/weekly_backtest.csv", "holdouts": validation}
        args.validation_output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=args.validation_output.parent, delete=False) as staged:
            staged.write((json.dumps(report, indent=2) + "\n").encode())
        Path(staged.name).chmod(0o644)
        Path(staged.name).replace(args.validation_output)
        print(f"Verified 104 archived city totals. Replay SHA-256 {hashlib.sha256(args.output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
