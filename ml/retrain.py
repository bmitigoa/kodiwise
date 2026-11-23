"""One command for the monthly retrain. Stops before deploying.

    python -m ml.retrain                       # newest datasets/ file in the scrape bucket
    python -m ml.retrain --dataset PATH.csv    # a local file instead
    python -m ml.retrain --report-only         # data checks only: no training, nothing saved

Steps (CLAUDE.md rule 4 and the Phase 4 plan):
  1. Data report: rows per neighbourhood before vs now, confidence-tier changes,
     amenity-flag drift (stops if any flag moves > 10 points), anomalies in new rows.
  2. Train the candidate with the SAME feature set as the version currently served
     (read from api/main.py + its metrics.json) and save it as a new immutable version.
  3. Deploy gate vs the served version on the same rows, 5 seeds: mean test MAPE and
     mean STRICT CV R2 (scored on the served version's training rows only; new rows
     always train). Loose CV, errors by confidence group and by area on the new rows
     are reported alongside.
  4. Checks: Kileleshwa vs Lavington 3-bed, size of the Furnished factor, thin areas.

It never edits the API, the Dockerfile or the README and never deploys. Deploying
a version that passes is a separate, reviewed step.

Exit codes: 0 gate passed | 1 gate failed | 2 usage / data error | 4 amenity-flag drift (stopped).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.derive import fingerprint_hash
from ml.evaluate import normalize_ids
from ml.features import (
    FEATURE_SETS,
    STRATIFY_COL,
    TARGET,
    location_confidence,
    recompute_rooms_bath_from_counts,
)
from ml.train import MODELS_DIR, SNAPSHOT_DIR, run_experiment

ROOT = Path(__file__).resolve().parent.parent
FLAG_COLS = ["has_generator", "has_borehole", "has_cctv", "has_dsq", "has_play_area", "has_garden", "is_furnished"]
FLAG_DRIFT_STOP_PP = 10.0
FURNISHED_FLAG_SHARE = 0.25
OUTLIER_RATIO = 2.0
TRAIN_SHARE = 0.8          # rough share of rows in the training split (exact counts come after training)
THIN_AREAS = ("Upperhill", "Loresho", "Gigiri")
# Carried into every retrain report so the open items from the last deploy are looked at again.
NEXT_RETRAIN_CHECKLIST = [
    "Strict CV R2: v20261123-appF was 0.004 lower than appE2 (negative in all 5 seeds, within the 0.01 limit). "
    "Check the next candidate's strict CV R2 against appF; a second small drop in a row is a reason to stop and ask.",
    "Furnished factor: 37-50% of a furnished estimate in appF (26-47% in appE2; furnished = 15% of rows, median rent "
    "KES 140,000 vs 60,000). Re-check the 'furnished_factor' share in this report; look for more furnished/unfurnished "
    "pairs in the same area and size before trusting the effect.",
    "Loresho (and Upperhill, Gigiri): 7, 9 and 4 training rows in appF. Loresho 1-bed moved KES 67,000 -> 31,000. "
    "Compare the thin_areas section with appF's and check they now have more rows.",
    "'none' confidence group out-of-fold MAPE was 2 points worse in appF (17 rows); check it has not worsened again.",
]

EXIT_OK, EXIT_GATE_FAILED, EXIT_DATA, EXIT_FLAG_DRIFT = 0, 1, 2, 4


# ---------------------------------------------------------------- inputs
def served_version(main_py: Path = ROOT / "api" / "main.py") -> str:
    m = re.search(r'^PRODUCTION_VERSION\s*=\s*"([^"]+)"', main_py.read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError("PRODUCTION_VERSION not found in api/main.py")
    return m.group(1)


def load_dataset(path: str | None, bucket: str | None) -> tuple[pd.DataFrame, str]:
    if path:
        return pd.read_csv(path), Path(path).name
    from data_pipeline.job import GcsStore, latest_dataset
    store = GcsStore(bucket or "rent-prediction-ar-kodiwise-scrape")
    name = latest_dataset(store)
    return pd.read_csv(io.BytesIO(store.read(name))), name


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Dataset -> training frame: rows are identified by the fingerprint hash; rooms_total and
    bath_per_bed are recomputed from the counts (what the API can reproduce)."""
    d = df.copy()
    if "fingerprint" not in d.columns:
        d["fingerprint"] = d["fingerprint_hash"]
    if "title_clean" not in d.columns:      # new datasets keep no title text; this feature set has no text feature
        d["title_clean"] = ""
    return recompute_rooms_bath_from_counts(normalize_ids(d))


def load_served_data(version: str) -> pd.DataFrame:
    return normalize_ids(pd.read_csv(SNAPSHOT_DIR / f"{version}.csv"))


# ---------------------------------------------------------------- step 1: data
def area_report(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    co, cn = old["location_std"].value_counts(), new["location_std"].value_counts()
    rows = []
    for loc in sorted(set(co.index) | set(cn.index)):
        a, b = int(co.get(loc, 0)), int(cn.get(loc, 0))
        rows.append({"area": loc, "before": a, "now": b, "added": b - a,
                     "tier_before": location_confidence(round(a * TRAIN_SHARE)),
                     "tier_now": location_confidence(round(b * TRAIN_SHARE))})
    return pd.DataFrame(rows).sort_values("now").reset_index(drop=True)


def flag_drift(old: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    """Amenity flag rates (%) of new rows vs the old Jiji rows (same source, same text method)."""
    base = old[old["platform"] == "Jiji"] if "platform" in old.columns and (old["platform"] == "Jiji").any() else old
    rows = []
    for f in FLAG_COLS:
        if f in base.columns and f in fresh.columns:
            o, n = 100 * base[f].mean(), 100 * fresh[f].mean()
            rows.append({"flag": f, "old_pct": round(o, 1), "new_pct": round(n, 1), "diff_pp": round(n - o, 1)})
    return pd.DataFrame(rows)


def anomalies(old: pd.DataFrame, fresh: pd.DataFrame) -> dict:
    """Simple screens on the new rows only (nothing is dropped here)."""
    out: dict = {"n_new_rows": int(len(fresh))}
    allr = pd.concat([old.assign(_src="old"), fresh.assign(_src="new")], ignore_index=True)
    allr["_lp"] = np.log(allr[TARGET].astype(float))
    g = allr.groupby(["location_std", "bedrooms_num"])["_lp"]
    allr["_ratio"] = np.exp(allr["_lp"] - g.transform("median"))
    allr["_n"] = g.transform("size")
    f = allr[(allr["_src"] == "new") & (allr["_n"] >= 4)]
    odd = f[(f["_ratio"] > OUTLIER_RATIO) | (f["_ratio"] < 1 / OUTLIER_RATIO)]
    out["price_outliers_vs_area_beds_median"] = {
        "checked": int(len(f)), "flagged": int(len(odd)),
        "rows": odd[["location_std", "bedrooms_num", TARGET, "_ratio"]].round(2).rename(columns={"_ratio": "ratio"})
        .to_dict("records")}
    out["duplicate_listing_ids"] = int(fresh["listing_id"].duplicated().sum()) if "listing_id" in fresh else None
    out["same_area_price_beds_baths_rows"] = int(
        fresh.duplicated(["location_std", TARGET, "bedrooms_num", "bathrooms_num"], keep=False).sum())
    out["sq_m_outside_15_1000"] = int(((fresh["sq_m"] < 15) | (fresh["sq_m"] > 1000)).sum())
    out["price_range"] = [float(fresh[TARGET].min()), float(fresh[TARGET].max())]
    out["bedrooms"] = {str(k): int(v) for k, v in fresh["bedrooms_num"].value_counts().sort_index().items()}
    return out


# ---------------------------------------------------------------- step 4: checks
def _load_predictor(version: str):
    from api.predictor import Predictor
    p = Predictor(version)
    p.load()
    return p


def check_kileleshwa_vs_lavington(preds: dict) -> dict:
    out = {}
    for ver, p in preds.items():
        rows = {}
        for sq in (None, 120.0):
            r = {a: p.predict(3, 2, a, sq_m=sq, explain=False) for a in ("Kileleshwa", "Lavington")}
            rows["size_not_given" if sq is None else "120_m2"] = {
                a: {"estimate": r[a]["predicted_rent_kes"], "low": r[a]["predicted_rent_low_kes"],
                    "high": r[a]["predicted_rent_high_kes"], "confidence": r[a]["location_confidence"]}
                for a in r}
            rows["size_not_given" if sq is None else "120_m2"]["kileleshwa_minus_lavington"] = round(
                r["Kileleshwa"]["predicted_rent_kes"] - r["Lavington"]["predicted_rent_kes"], 0)
        out[ver] = rows
    return out


def furnished_effect(p, beds: int, baths: int, area: str) -> dict:
    """Size of the Furnished factor in the explanation of a furnished listing, and the
    plain difference between predicting it furnished and not."""
    from ml.explain import FEATURE_TO_GROUP, contributions, kes_effect
    on = p.predict(beds, baths, area, is_furnished=1, explain=False)
    off = p.predict(beds, baths, area, is_furnished=0, explain=False)
    row, *_ = p.build_row(beds, baths, area, None, 1, None, None, None, None, None, None, None)
    names, contrib, _ = contributions(p.pipe, row)
    c = sum(float(v) for n, v in zip(names, contrib) if FEATURE_TO_GROUP.get(n) == "Furnished")
    est = on["predicted_rent_kes"]
    eff = kes_effect(est, c)
    return {"case": f"{beds}-bed {baths}-bath {area}", "estimate_furnished": est,
            "estimate_not_furnished": off["predicted_rent_kes"],
            "furnished_factor_kes": round(eff, 0), "share_of_estimate": round(eff / est, 3) if est else None,
            "flag": bool(est and abs(eff) / est > FURNISHED_FLAG_SHARE)}


def check_furnished(preds: dict, train_df: pd.DataFrame) -> dict:
    cases = [(2, 2, "Kilimani"), (3, 3, "Kileleshwa"), (1, 1, "Westlands"), (2, 2, "Utawala")]
    out = {"furnished_share_of_training_rows_pct": round(100 * float(train_df["is_furnished"].mean()), 1),
           "furnished_median_price": float(train_df.loc[train_df["is_furnished"] == 1, TARGET].median()),
           "not_furnished_median_price": float(train_df.loc[train_df["is_furnished"] == 0, TARGET].median()),
           "threshold_share_of_estimate": FURNISHED_FLAG_SHARE, "versions": {}}
    for ver, p in preds.items():
        out["versions"][ver] = [furnished_effect(p, *c) for c in cases]
    return out


def check_thin_areas(preds: dict, counts_now: dict) -> dict:
    out = {}
    for area in THIN_AREAS:
        per = {}
        for ver, p in preds.items():
            lk = p.location_lookup.get(area, {})
            est = []
            for beds, baths in ((1, 1), (2, 2), (3, 2)):
                r = p.predict(beds, baths, area, explain=False)
                est.append({"beds": beds, "baths": baths, "estimate": r["predicted_rent_kes"],
                            "low": r["predicted_rent_low_kes"], "high": r["predicted_rent_high_kes"],
                            "confidence": r["location_confidence"]})
            per[ver] = {"train_rows": lk.get("loc_count_tr"), "estimates": est}
        out[area] = {"rows_in_dataset": counts_now.get(area, 0), **per}
    return out


# ---------------------------------------------------------------- reporting
def tier_changes(old_lookup: dict, new_lookup: dict) -> list[dict]:
    rows = []
    for area in sorted(set(old_lookup) | set(new_lookup)):
        if area == "__global__":
            continue
        a = (old_lookup.get(area) or {}).get("loc_count_tr", 0.0)
        b = (new_lookup.get(area) or {}).get("loc_count_tr", 0.0)
        ta, tb = location_confidence(a), location_confidence(b)
        if ta != tb or a != b:
            rows.append({"area": area, "train_rows_before": a, "train_rows_now": b, "tier_before": ta, "tier_now": tb})
    return rows


def _print_table(title: str, df: pd.DataFrame) -> None:
    print(f"\n{title}\n{df.to_string(index=False)}")


def print_data_report(report: dict) -> None:
    print(f"\n=== 1. Data: {report['dataset']} ({report['rows_now']} rows; served data {report['rows_before']}) ===")
    _print_table("Rows per neighbourhood (tiers use ~80% of rows as training rows)",
                 pd.DataFrame(report["areas"]))
    _print_table("Amenity flags: new rows vs old Jiji rows (stop if any > "
                 f"{FLAG_DRIFT_STOP_PP:.0f} pp)", pd.DataFrame(report["flag_drift"]))
    a = report["anomalies"]
    print(f"\nNew-row screens: {a['n_new_rows']} rows | price {a['price_range']} | duplicate ids {a['duplicate_listing_ids']} "
          f"| same area/price/beds/baths rows {a['same_area_price_beds_baths_rows']} | sq_m out of range {a['sq_m_outside_15_1000']}")
    o = a["price_outliers_vs_area_beds_median"]
    print(f"Price outliers (> {OUTLIER_RATIO:.0f}x or < 1/{OUTLIER_RATIO:.0f} of the area+beds median): {o['flagged']} of {o['checked']}")


def print_gate(gate: dict) -> None:
    cur, cand = gate["current"]["summary"], gate["candidate"]["summary"]

    def f(s, k, nd=3):
        return f"{s[k]['mean']:.{nd}f} (std {s[k]['std']:.{nd}f}, {s[k]['min']:.{nd}f}-{s[k]['max']:.{nd}f})"

    print(f"\n=== 3. Deploy gate vs {gate['current_version']}: {'PASSES' if gate['passes'] else 'FAILS'} ===")
    print(gate["rule"])
    print(f"rows: {gate['rows']}")
    print(f"test MAPE   current {f(cur, 'test_mape', 2)} | candidate {f(cand, 'test_mape', 2)} | delta {gate['test_mape_delta_pp']:+.2f} pp")
    print(f"strict CV R2 current {f(cur, 'cv_r2')} | candidate {f(cand, 'cv_r2')} | delta {gate['cv_r2_delta']:+.4f}   <- gate")
    print(f"loose CV R2  current {f(cur, 'cv_r2_loose')} | candidate {f(cand, 'cv_r2_loose')} | delta {gate['cv_r2_delta_loose']:+.4f}   (information)")
    print(f"paired per-seed deltas: {json.dumps(gate['paired_seed_deltas'])}")
    for part in ("cv_oof", "test"):
        for g, v in gate["by_confidence"][part].items():
            print(f"  {part:6s} {g:5s} n={v['n_rows']:4d}  MAPE current {v['current']['MAPE']['mean']:.1f} -> "
                  f"candidate {v['candidate']['MAPE']['mean']:.1f}  (paired {v['mape_delta_pp']['mean']:+.2f} pp)")
    nb = gate.get("new_rows_by_area") or {}
    if nb:
        rows = [{"area": k, **v} for k, v in nb.items()]
        _print_table("Error on the NEW rows by area (current version never saw them; candidate out-of-fold). Not part of the gate.",
                     pd.DataFrame(rows).round(1))


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", help="local CSV (default: newest datasets/ file in the scrape bucket)")
    ap.add_argument("--bucket", help="scrape bucket name (default rent-prediction-ar-kodiwise-scrape)")
    ap.add_argument("--version", help="new version name (default v<today>-app<next letter>)")
    ap.add_argument("--current", help="version to compare with (default: PRODUCTION_VERSION in api/main.py)")
    ap.add_argument("--report-only", action="store_true", help="step 1 only: nothing trained or saved")
    ap.add_argument("--allow-flag-drift", action="store_true", help="continue although a flag moved > 10 pp")
    args = ap.parse_args(argv)

    current = args.current or served_version()
    cur_metrics = json.loads((MODELS_DIR / current / "metrics.json").read_text())
    fs = FEATURE_SETS[cur_metrics["feature_set"]]
    raw, dataset_name = load_dataset(args.dataset, args.bucket)
    new_df = prepare(raw)
    old_df = load_served_data(current)
    missing = [c for c in fs.numeric + fs.binary + [TARGET, STRATIFY_COL, "location_std"] if c not in new_df.columns
               and c not in ("lat", "lon") and not c.startswith("dist_") and not c.startswith("loc_")]
    if missing:
        print(f"dataset is missing columns the model needs: {missing}")
        return EXIT_DATA

    fresh = new_df[~new_df["fingerprint"].isin(set(old_df["fingerprint"]))]
    report: dict = {"generated": date.today().isoformat(), "dataset": dataset_name, "current_version": current,
                    "feature_set": fs.name, "rows_before": len(old_df), "rows_now": len(new_df),
                    "rows_new": len(fresh), "rows_served_missing_from_dataset": int(
                        (~old_df["fingerprint"].isin(set(new_df["fingerprint"]))).sum())}
    report["areas"] = area_report(old_df, new_df).to_dict("records")
    drift = flag_drift(old_df, fresh)
    report["flag_drift"] = drift.to_dict("records")
    report["anomalies"] = anomalies(old_df, fresh)
    print_data_report(report)

    worst = float(drift["diff_pp"].abs().max()) if len(drift) else 0.0
    if worst > FLAG_DRIFT_STOP_PP and not args.allow_flag_drift:
        print(f"\nSTOP: an amenity flag moved {worst:.1f} pp (> {FLAG_DRIFT_STOP_PP:.0f}). Not training. "
              "Tell Baraka; --allow-flag-drift continues once he agrees.")
        return EXIT_FLAG_DRIFT
    if args.report_only:
        return EXIT_OK

    letter = chr(ord("F") + sum(1 for p in MODELS_DIR.glob(f"v{date.today():%Y%m%d}-app*")))
    version = args.version or f"v{date.today():%Y%m%d}-app{letter}"
    print(f"\n=== 2. Training {version} (feature set {fs.name}, compared with {current}) ===")
    result = run_experiment(new_df, fs, save_model=True, version=version, compare_to=current,
                            data_source=f"bucket:{dataset_name}" if not args.dataset else dataset_name)
    gate = result["deploy_comparison"]
    report.update({"candidate_version": version, "test_metrics": result["test_metrics"],
                   "cv_lgbm_log_target": result["cv_lgbm_log_target"], "gate": gate})
    print(f"test: {json.dumps(result['test_metrics'])}")
    print_gate(gate)

    print("\n=== 4. Checks ===")
    preds = {current: _load_predictor(current), version: _load_predictor(version)}
    report["tier_changes"] = tier_changes(preds[current].location_lookup, preds[version].location_lookup)
    _print_table("Tier changes from the real training split", pd.DataFrame(report["tier_changes"]))
    report["kileleshwa_vs_lavington_3bed"] = check_kileleshwa_vs_lavington(preds)
    print("\nKileleshwa vs Lavington, 3-bed 2-bath:", json.dumps(report["kileleshwa_vs_lavington_3bed"], indent=1))
    report["furnished"] = check_furnished(preds, new_df)
    print("\nFurnished factor:", json.dumps(report["furnished"], indent=1))
    counts = new_df["location_std"].value_counts().to_dict()
    report["thin_areas"] = check_thin_areas(preds, counts)
    report["next_retrain_checklist"] = NEXT_RETRAIN_CHECKLIST
    print("\nThin areas:", json.dumps(report["thin_areas"], indent=1))
    print("\nChecklist for the next retrain:\n- " + "\n- ".join(NEXT_RETRAIN_CHECKLIST))

    out = MODELS_DIR / version / "retrain_report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nReport saved to {out}")
    print("Gate " + ("PASSED" if gate["passes"] else "FAILED") + ". Nothing was deployed: "
          "review the report, then decide (a miss needs Baraka's call).")
    return EXIT_OK if gate["passes"] else EXIT_GATE_FAILED


if __name__ == "__main__":
    sys.exit(main())
