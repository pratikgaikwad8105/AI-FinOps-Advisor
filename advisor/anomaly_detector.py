# advisor/anomaly_detector.py
import pandas as pd
from pathlib import Path
from datetime import datetime
BASE_DIR = Path(__file__).resolve().parent.parent

def detect_hourly_anomalies():
    path = BASE_DIR / "advisor" / "billing_hourly.csv"
    if not path.exists():
        return []

    df = pd.read_csv(path)
    if df.empty:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["hour"] = df["timestamp"].dt.hour

    base = df.groupby(["service","hour"], as_index=False)["cost"].mean().rename(columns={"cost":"baseline"})
    df = df.merge(base, on=["service","hour"], how="left")
    df["baseline"] = df["baseline"].fillna(df["cost"].mean() or 1.0)
    df["deviation"] = (df["cost"] - df["baseline"]) / df["baseline"].replace({0:1})

    anomalies = []
    for _, r in df[df["deviation"] > 0.40].iterrows():
        dev_pct = round(r["deviation"] * 100, 1)
        if dev_pct > 120:
            sev = "HIGH"
        elif dev_pct > 70:
            sev = "MEDIUM"
        else:
            sev = "LOW"
        ts = r["timestamp"]
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if not pd.isna(ts) else str(r.get("timestamp"))
        anomalies.append({
            "timestamp": ts_str,
            "service": r.get("service","N/A"),
            "description": f"{dev_pct}% above normal usage",
            "severity": sev
        })

    # return newest first
    anomalies_sorted = sorted(anomalies, key=lambda x: x["timestamp"], reverse=True)
    return anomalies_sorted
