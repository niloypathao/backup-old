import argparse
import numpy as np
import pandas as pd


def safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return numeric series with NaNs for non-numeric values."""
    if col not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[col], errors="coerce")


def compute_metrics(s: pd.Series) -> dict:
    """
    Compute metrics for a numeric series (km).
    Here we treat the input series as a deviation series (can be + or -).
    """
    s = s.dropna()

    # Full metric names (consistent order)
    if s.empty:
        return {
            "Count (valid rows)": 0,
            "Mean deviation (km)": np.nan,
            "Median deviation (km)": np.nan,
            "Standard deviation (km)": np.nan,
            "Minimum deviation (km)": np.nan,
            "Maximum deviation (km)": np.nan,
            "25th percentile deviation (km)": np.nan,
            "75th percentile deviation (km)": np.nan,
            "Interquartile range IQR (km)": np.nan,
            "Skewness": np.nan,
            "Kurtosis": np.nan,
            "Mean absolute error MAE (km)": np.nan,
            "Root mean squared error RMSE (km)": np.nan,
            "Mean absolute percentage error MAPE (%)": np.nan,
            "Positive deviation count": 0,
            "Negative deviation count": 0,
            "Zero deviation count": 0,
            "Positive deviation percentage (%)": np.nan,
            "Negative deviation percentage (%)": np.nan,
            "Count |deviation| ≤ 0.5 km": 0,
            "Percent |deviation| ≤ 0.5 km (%)": np.nan,
            "Count |deviation| > 0.5 km": 0,
            "Percent |deviation| > 0.5 km (%)": np.nan,
        }

    abs_s = s.abs()

    q25 = s.quantile(0.25)
    q75 = s.quantile(0.75)
    iqr = q75 - q25

    pos = int((s > 0).sum())
    neg = int((s < 0).sum())
    zero = int((s == 0).sum())

    metrics = {
        "Count (valid rows)": int(s.count()),
        "Mean deviation (km)": float(s.mean()),
        "Median deviation (km)": float(s.median()),
        "Standard deviation (km)": float(s.std(ddof=1)) if s.count() > 1 else 0.0,
        "Minimum deviation (km)": float(s.min()),
        "Maximum deviation (km)": float(s.max()),
        "25th percentile deviation (km)": float(q25),
        "75th percentile deviation (km)": float(q75),
        "Interquartile range IQR (km)": float(iqr),
        "Skewness": float(s.skew()) if s.count() > 2 else np.nan,
        "Kurtosis": float(s.kurtosis()) if s.count() > 3 else np.nan,
        "Mean absolute error MAE (km)": float(abs_s.mean()),
        "Root mean squared error RMSE (km)": float(np.sqrt(np.mean(np.square(s)))),
        "Mean absolute percentage error MAPE (%)": np.nan,  # filled later
        "Positive deviation count": pos,
        "Negative deviation count": neg,
        "Zero deviation count": zero,
        "Positive deviation percentage (%)": float(pos / len(s) * 100.0),
        "Negative deviation percentage (%)": float(neg / len(s) * 100.0),
        "Count |deviation| ≤ 0.5 km": int((abs_s <= 0.5).sum()),
        "Percent |deviation| ≤ 0.5 km (%)": float((abs_s <= 0.5).mean() * 100.0),
        "Count |deviation| > 0.5 km": int((abs_s > 0.5).sum()),
        "Percent |deviation| > 0.5 km (%)": float((abs_s > 0.5).mean() * 100.0),
    }

    return metrics


def add_mape_if_possible(df: pd.DataFrame, dev_col: str, gd_col: str = "Google Distance") -> float:
    """
    Compute MAPE% using deviation and Google Distance (km):
        mean(|dev| / GoogleDistance) * 100
    """
    if dev_col not in df.columns or gd_col not in df.columns:
        return np.nan

    dev = pd.to_numeric(df[dev_col], errors="coerce")
    gd = pd.to_numeric(df[gd_col], errors="coerce")

    mask = dev.notna() & gd.notna() & (gd != 0)
    if mask.sum() == 0:
        return np.nan

    return float((dev[mask].abs() / gd[mask]).mean() * 100.0)


def main(input_csv: str, output_csv: str):
    df = pd.read_csv(input_csv)

    bike_dev = safe_series(df, "deviation_bike")
    car_dev = safe_series(df, "deviation_car")

    bike_metrics = compute_metrics(bike_dev)
    car_metrics = compute_metrics(car_dev)

    # Fill MAPE%
    bike_metrics["Mean absolute percentage error MAPE (%)"] = add_mape_if_possible(df, "deviation_bike")
    car_metrics["Mean absolute percentage error MAPE (%)"] = add_mape_if_possible(df, "deviation_car")

    matrix = pd.DataFrame(
        {
            "Deviation (Bike)": bike_metrics,
            "Deviation (Car)": car_metrics,
        }
    )

    # Round numeric values nicely (keep counts as integers)
    def maybe_round(x):
        if isinstance(x, (int, np.integer)):
            return x
        try:
            if pd.isna(x):
                return x
            return round(float(x), 4)
        except Exception:
            return x

    matrix = matrix.applymap(maybe_round)

    matrix.to_csv(output_csv, index=True)
    print(f"[INFO] Saved matrix metrics -> {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create matrix metrics (bike vs car deviations) from output.csv")
    parser.add_argument("--input", required=True, help="Input CSV (your existing output.csv)")
    parser.add_argument("--output", default="matrix.csv", help="Output matrix CSV (default: matrix.csv)")
    args = parser.parse_args()

    main(args.input, args.output)
