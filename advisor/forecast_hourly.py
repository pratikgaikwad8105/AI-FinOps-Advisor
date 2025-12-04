# advisor/forecast_hourly.py
import pandas as pd
from prophet import Prophet
from pathlib import Path
from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)

def train_and_forecast_hourly():
    path = BASE_DIR / "advisor" / "billing_hourly.csv"
    df = pd.read_csv(path)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Prophet needs ds and y
    df = df.rename(columns={"timestamp": "ds", "cost": "y"})
    df = df[["ds", "y"]]

    model = Prophet()

    try:
        model.fit(df)
    except:
        # fallback
        df["yhat"] = df["y"]
        df["ds"] = pd.to_datetime(df["ds"])
        return df

    # Predict next 24 hours
    future = model.make_future_dataframe(periods=24, freq="H")
    forecast = model.predict(future)

    forecast = forecast[["ds", "yhat"]]
    return forecast
