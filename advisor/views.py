import json
import random
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.shortcuts import render, redirect


BASE_DIR = Path(settings.BASE_DIR)

from .forecast_model import train_and_forecast
from .anomaly_detector import detect_hourly_anomalies
from .recommendations import get_recommendations


# -----------------------------------------------------
# LIVE HOURLY SIMULATOR (5 sec = 1 hour)
# -----------------------------------------------------
def generate_live_hourly_data():
    csv_path = BASE_DIR / "advisor" / "billing_hourly.csv"

    if not csv_path.exists():
        return  # data_generator.py should create this file once

    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    if df.empty:
        return

    last_time = df["timestamp"].max()
    next_time = last_time + timedelta(hours=1)

    # normal baseline
    baseline = round(random.uniform(5.0, 15.0), 2)

    # anomaly state
    anomaly_flag = BASE_DIR / "advisor" / "anomaly_flag.txt"
    anomaly_active = anomaly_flag.exists()

    if anomaly_active:
        cost = round(baseline * random.uniform(3.0, 5.0), 2)  # spike
    else:
        cost = baseline

    new_row = {
        "timestamp": next_time.strftime("%Y-%m-%d %H:%M:%S"),
        "service": random.choice(["EC2", "S3", "RDS", "CloudFront"]),
        "cost": cost
    }

    df.loc[len(df)] = new_row
    df.to_csv(csv_path, index=False)


# -----------------------------------------------------
# DASHBOARD VIEW
# -----------------------------------------------------
def dashboard(request):
    # simulate next hour
    generate_live_hourly_data()

    hourly_path = BASE_DIR / "advisor" / "billing_hourly.csv"
    daily_path = BASE_DIR / "advisor" / "billing_daily.csv"

    df_hourly = pd.read_csv(hourly_path)
    df_hourly["timestamp"] = pd.to_datetime(df_hourly["timestamp"], errors="coerce")

    # load daily billing for forecast
    if daily_path.exists():
        df_daily = pd.read_csv(daily_path)
    else:
        df_daily = pd.DataFrame(columns=["date", "total_cost"])

    # FORECAST (uses your Prophet code)
    forecast_df = train_and_forecast()

    # DAILY GRAPH PREP
    daily_chart = []
    for _, r in forecast_df.tail(30).iterrows():
        ds = r["ds"]
        ds_str = ds.strftime("%Y-%m-%d") if hasattr(ds, "strftime") else str(ds)

        daily_chart.append({
            "date": ds_str,
            "actual": float(r["y"]) if not pd.isna(r["y"]) else None,
            "predicted": float(r["yhat"]),
        })

    # HOURLY GRAPH PREP (last 48 hrs)
    last_hours = df_hourly.tail(48)
    hourly_chart = [
        {
            "timestamp": r["timestamp"].strftime("%Y-%m-%d %H:%M"),
            "service": r["service"],
            "cost": float(r["cost"]),
        }
        for _, r in last_hours.iterrows()
    ]

    # ANOMALIES
    anomalies = detect_hourly_anomalies()

    severity_order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}

    def sort_key(a):
        sev = severity_order.get(a["severity"], 3)
        try:
            t = datetime.strptime(a["timestamp"], "%Y-%m-%d %H:%M")
            return (sev, -t.timestamp())
        except:
            return (sev, 0)

    sorted_anomalies = sorted(anomalies, key=sort_key)
    top_anomalies = sorted_anomalies[:3]

    # RECOMMENDATIONS
    recs = get_recommendations()
    top_recs = sorted(recs, key=lambda x: x["savings_value"], reverse=True)[:3]

    # SUMMARY VALUES
    if not df_daily.empty:
        last_30 = df_daily.tail(30)
        prev_30 = df_daily.tail(60).head(30)

        total_cost = round(last_30["total_cost"].sum(), 2)
        if not prev_30.empty:
            change = round(((last_30["total_cost"].sum() - prev_30["total_cost"].sum()) /
                            prev_30["total_cost"].sum()) * 100, 2)
        else:
            change = 0.0
    else:
        total_cost = 0.0
        change = 0.0

    next_month_pred = round(forecast_df.tail(30)["yhat"].sum(), 2)
    savings = round(next_month_pred - total_cost, 2)

    summary = {
        "total_cost": total_cost,
        "change_percentage": change,
        "predicted_next_month": next_month_pred,
        "savings": savings,
    }

    context = {
        "summary": summary,
        "daily_chart_json": json.dumps(daily_chart),
        "hourly_chart_json": json.dumps(hourly_chart),
        "top_anomalies": top_anomalies,
        "top_recs": top_recs,
    }

    return render(request, "advisor/dashboard.html", context)


# -----------------------------------------------------
# FULL LIST PAGES
# -----------------------------------------------------
def anomalies_list(request):
    anomalies = detect_hourly_anomalies()
    return render(request, "advisor/anomalies.html", {"anomalies": anomalies})


def recommendations_list(request):
    recs = get_recommendations()
    return render(request, "advisor/recommendations.html", {"recs": recs})


# -----------------------------------------------------
# ANOMALY BUTTON ACTIONS
# -----------------------------------------------------
def force_anomaly(request):
    flag = BASE_DIR / "advisor" / "anomaly_flag.txt"
    flag.write_text("1")
    return redirect("dashboard")


def solve_anomaly(request):
    flag = BASE_DIR / "advisor" / "anomaly_flag.txt"
    if flag.exists():
        flag.unlink()
    return redirect("dashboard")


def index(request):
    return render(request, "advisor/index.html")


# LOGIN VIEW
def login_user(request):
    if request.method == "POST":
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")

        # Convert email → username
        username = email.split("@")[0]

        user = authenticate(request, username=username, password=password)

        if user is None:
            return render(request, "advisor/login.html", {
                "error": "Invalid email or password."
            })

        login(request, user)
        return redirect("dashboard")

    return render(request, "advisor/login.html")


# REGISTER VIEW
def register_user(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()

        if not full_name or not email or not password:
            return render(request, "advisor/register.html", {
                "error": "All fields are required."
            })

        if "@" not in email:
            return render(request, "advisor/register.html", {
                "error": "Enter a valid email address."
            })

        # Split full name safely
        name_parts = full_name.split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        if User.objects.filter(email=email).exists():
            return render(request, "advisor/register.html", {
                "error": "Email is already registered."
            })

        username = email.split("@")[0]

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        login(request, user)
        return redirect("dashboard")

    return render(request, "advisor/register.html")



# LOGOUT
def logout_user(request):
    logout(request)
    return redirect("login")


# PROFILE PAGE
def profile_page(request):
    return render(request, "advisor/profile.html")
