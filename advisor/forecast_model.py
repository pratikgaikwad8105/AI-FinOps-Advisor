import pandas as pd
from prophet import Prophet
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def train_and_forecast():

    # Load daily data
    df = pd.read_csv(BASE_DIR / "advisor" / "billing_daily.csv")

    # Ensure the correct columns exist
    if "date" not in df.columns or "total_cost" not in df.columns:
        raise ValueError("billing_daily.csv must contain 'date' and 'total_cost' columns")

    # Convert date to datetime
    df["date"] = pd.to_datetime(df["date"])

    # Prophet requires columns: ds (date) and y (value)
    df.rename(columns={"date": "ds", "total_cost": "y"}, inplace=True)

    # Ensure numeric
    df["y"] = pd.to_numeric(df["y"], errors="coerce").fillna(0)

    # Train model
    model = Prophet()

    try:
        model.fit(df)
    except Exception as e:
        print("Prophet training failed:", e)
        # Return a fallback dataframe to avoid dashboard crash
        df["yhat"] = df["y"]
        df["yhat_lower"] = df["y"]
        df["yhat_upper"] = df["y"]
        df.rename(columns={"ds": "date"}, inplace=True)
        return df.rename(columns={"date": "ds"})

    # Forecast next 30 days
    future = model.make_future_dataframe(periods=30)
    forecast = model.predict(future)

    # Convert forecast['ds'] to datetime
    forecast["ds"] = pd.to_datetime(forecast["ds"])

    # Select needed fields
    forecast = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]

    # Merge with original daily actuals
    merged = df.merge(forecast, on="ds", how="right")

    return merged

