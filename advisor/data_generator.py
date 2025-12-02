import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SERVICES = [
    {"name": "EC2", "category": "Compute"},
    {"name": "RDS", "category": "Database"},
    {"name": "S3", "category": "Storage"},
    {"name": "CloudFront", "category": "Network"},
]

def create_advanced_billing_data():
    
    dates = pd.date_range(start="2024-01-01", end="2024-03-31", freq="D")

    hourly_rows = []

    for d in dates:
        day_index = (d - dates[0]).days
        weekday = d.weekday()  # 0=Mon, 6=Sun

        # Base total cost trend: grows slowly over time
        base_total = 40 + day_index * 0.25

        # Weekday vs weekend pattern
        if weekday < 5:   # Mon–Fri
            total_for_day = base_total + np.random.normal(8, 3)
        else:             # Sat–Sun
            total_for_day = base_total - 8 + np.random.normal(3, 2)

        # Split total cost into services using fixed ratios
        ratios = {
            "EC2": 0.45,
            "RDS": 0.25,
            "S3":  0.20,
            "CloudFront": 0.10,
        }

        # Split the daily cost into 24 hours
        hours = pd.date_range(start=d, periods=24, freq="H")

        for hour_ts in hours:
            # Hour-of-day pattern (peak during working hours)
            hour = hour_ts.hour
            if 9 <= hour <= 18:  # office-hours peak
                hour_factor = 1.15
            elif 0 <= hour <= 5: # low at night
                hour_factor = 0.6
            else:
                hour_factor = 0.9

            # Hourly base for the whole day (total_for_day / 24)
            hour_base = (total_for_day / 24.0) * hour_factor

            for svc in SERVICES:
                # small random variation per service per hour
                noise = np.random.normal(0, hour_base * 0.05)
                cost = max(0, hour_base * ratios[svc["name"]] + noise)

                hourly_rows.append({
                    "timestamp": hour_ts,             # full datetime
                    "date": d.date(),                 # only date part
                    "hour": hour,                     # 0..23
                    "service": svc["name"],
                    "category": svc["category"],
                    "cost": round(cost, 2),
                })

    df_hourly = pd.DataFrame(hourly_rows)

    # Inject realistic anomalies on some random hourly rows
    rng = np.random.default_rng(42)  # fixed seed → reproducible
    anomaly_indices = rng.choice(len(df_hourly), size=20, replace=False)
    df_hourly.loc[anomaly_indices, "cost"] *= rng.uniform(1.8, 3.2, size=20)

    # Daily aggregated per service
    df_detailed_daily = (
        df_hourly.groupby(["date", "service", "category"], as_index=False)["cost"]
        .sum()
        .rename(columns={"cost": "daily_cost"})
    )

    # Daily total (for Prophet)
    df_daily_total = (
        df_hourly.groupby("date", as_index=False)["cost"]
        .sum()
        .rename(columns={"cost": "total_cost"})
    )

    out_dir = BASE_DIR / "advisor"
    out_dir.mkdir(exist_ok=True)

    # Save all three
    df_hourly.to_csv(out_dir / "billing_hourly.csv", index=False)
    df_detailed_daily.to_csv(out_dir / "billing_detailed.csv", index=False)
    df_daily_total.to_csv(out_dir / "billing_daily.csv", index=False)

    return df_daily_total, df_detailed_daily, df_hourly

if __name__ == "__main__":
    daily, detailed, hourly = create_advanced_billing_data()
    print("Generated billing_daily.csv, billing_detailed.csv, billing_hourly.csv")
