# advisor/forecast_model.py
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def train_and_forecast():
    """
    Wrapper required by views.py.
    Simply calls train_and_forecast_daily().
    """
    return train_and_forecast_daily()


def train_and_forecast_daily():
    """
    Train a Prophet model on billing_daily.csv.
    If Prophet is not installed or fails, fallback to simple rolling mean.
    Returns a DataFrame with: ds, y, yhat
    """
    try:
        from prophet import Prophet
    except Exception:
        Prophet = None

    csv_path = BASE_DIR / "advisor" / "billing_daily.csv"

    # If file missing → return empty forecast
    if not csv_path.exists():
        return pd.DataFrame(columns=["ds", "y", "yhat"])

    df = pd.read_csv(csv_path)

    # Ensure date column exists
    if "date" in df.columns:
        df["ds"] = pd.to_datetime(df["date"])
    elif "ds" in df.columns:
        df["ds"] = pd.to_datetime(df["ds"])
    else:
        raise ValueError("billing_daily.csv must contain 'date' or 'ds' column")

    # Ensure cost column exists
    if "total_cost" in df.columns:
        df["y"] = pd.to_numeric(df["total_cost"], errors="coerce").fillna(0)
    else:
        df["y"] = 0

    df = df[["ds", "y"]].sort_values("ds")

    # -----------------------------------------
    # CASE 1: Prophet installed → real forecasting
    # -----------------------------------------
    if Prophet is not None:
        try:
            model = Prophet(daily_seasonality=True)
            model.fit(df.rename(columns={"ds": "ds", "y": "y"}))

            future = model.make_future_dataframe(periods=30)
            forecast = model.predict(future)[["ds", "yhat"]]

            # Merge actual and predicted
            merged = df.merge(forecast, on="ds", how="right")
            return merged
        except Exception:
            pass  # fall back below

    # -----------------------------------------
    # CASE 2: Prophet missing → fallback forecast
    # -----------------------------------------
    # Simple rolling mean so prediction is NOT flat
    df["yhat"] = df["y"].rolling(window=7, min_periods=1).mean()
    return df
