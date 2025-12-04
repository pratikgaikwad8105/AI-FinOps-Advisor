# advisor/views.py
import json
import random
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponse

BASE_DIR = Path(__file__).resolve().parent
ADVISOR_DIR = BASE_DIR  # files live in advisor/

# Try to import long-term forecast helper. If missing, we continue without crash.
try:
    from advisor.forecast_model import train_and_forecast
except Exception as e:
    train_and_forecast = None

from .anomaly_detector import detect_hourly_anomalies
from .recommendations import get_recommendations
from .models import Profile
from django.contrib.auth.models import User

# helper read/write extra emails (simple file-based fallback removed: use Profile)
def read_extra_emails(username):
    try:
        u = User.objects.get(username=username)
        return u.profile.get_email_list()
    except Exception:
        return []

def write_extra_emails(username, emails_list):
    try:
        u = User.objects.get(username=username)
        u.profile.extra_emails = ",".join(emails_list)
        u.profile.save()
    except Exception:
        pass

# Append a simulated hour row to billing_hourly.csv
def append_one_live_hour(force=False):
    csv_path = ADVISOR_DIR / "billing_hourly.csv"
    if not csv_path.exists():
        # create an initial file with some synthetic data
        df = pd.DataFrame(columns=["timestamp", "service", "cost"])
        df.to_csv(csv_path, index=False)

    df = pd.read_csv(csv_path)
    now = datetime.now()
    svc = random.choice(["EC2", "S3", "RDS", "CloudFront"])
    baseline = round(random.uniform(8.0, 25.0), 2)

    # if force True -> big spike
    if force or random.random() < 0.02:
        cost = round(baseline * random.uniform(2.5, 5.0), 2)
    else:
        noise = random.normalvariate(0, baseline * 0.08)
        cost = round(max(0.1, baseline + noise), 2)

    new_row = {"timestamp": now.strftime("%Y-%m-%d %H:%M:%S"), "service": svc, "cost": cost}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(csv_path, index=False)
    return new_row

@login_required
def live_update(request):
    # if client asked to force anomaly (button), we set force=True
    force_flag = request.GET.get("force", "0") == "1"
    new_row = append_one_live_hour(force=force_flag)

    hourly_path = ADVISOR_DIR / "billing_hourly.csv"
    df_hourly = pd.read_csv(hourly_path)
    df_hourly["timestamp"] = pd.to_datetime(df_hourly["timestamp"], errors="coerce")
    df_total = df_hourly.groupby("timestamp", as_index=False)["cost"].sum().sort_values("timestamp")
    last_points = df_total.tail(72)

    hourly_chart = [{"timestamp": t.strftime("%Y-%m-%d %H:%M"), "cost": float(c)} for t, c in zip(last_points["timestamp"], last_points["cost"])]

    # simple short-term "prediction": linear extrapolation from last 6 points
    future = []
    if len(last_points) >= 6:
        window = last_points.tail(6).reset_index(drop=True)
        x = list(range(len(window)))
        coef = (window["cost"].iloc[-1] - window["cost"].iloc[0]) / max(1, (x[-1] - x[0]))
        last_ts = pd.to_datetime(window["timestamp"].iloc[-1])
        for i in range(1, 13):  # next 12 hours (demo)
            ts = (last_ts + pd.Timedelta(hours=i)).strftime("%Y-%m-%d %H:%M")
            pred_val = float(max(0.1, window["cost"].iloc[-1] + coef * i))
            future.append({"timestamp": ts, "predicted": round(pred_val, 2)})

    anomalies_all = detect_hourly_anomalies()
    # pick anomalies that match last appended timestamp (minute resolution)
    new_anoms = []
    if new_row:
        new_ts_min = datetime.strptime(new_row["timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M")
        for a in anomalies_all:
            if a.get("timestamp") == new_ts_min:
                new_anoms.append(a)

    # send email on new_anoms
    if new_anoms:
        try:
            user = request.user
            recipients = [user.email] if user.email else []
            recipients += read_extra_emails(user.username)
            subject = f"[CloudPulse AI] Anomaly detected at {new_ts_min}"
            body_lines = []
            for a in new_anoms:
                body_lines.append(f"{a['timestamp']} | {a['service']} | {a['severity']}\n{a['description']}\n")
            body = "\n".join(body_lines)
            if recipients:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
        except Exception as e:
            print("Email send failed:", e)

    # top 3 anomalies for UI
    top_anoms = sorted(anomalies_all, key=lambda x: x.get("timestamp", ""), reverse=True)[:3]

    # top recs
    recs = get_recommendations()
    top_recs = sorted(recs, key=lambda x: x.get("savings_value", 0), reverse=True)[:3]

    # summary numbers (from daily if exists)
    daily_path = ADVISOR_DIR / "billing_daily.csv"
    if daily_path.exists():
        df_daily = pd.read_csv(daily_path)
        total_cost = round(df_daily.tail(30)["total_cost"].sum(), 2) if not df_daily.empty else 0.0
    else:
        total_cost = round(df_total.tail(30)["cost"].sum(), 2) if not df_total.empty else 0.0

    # long-term forecast (if function exists)
    next_month_pred = 0.0
    if train_and_forecast:
        try:
            fdf = train_and_forecast()
            next_month_pred = round(float(fdf.tail(30)["yhat"].sum()), 2)
        except Exception:
            next_month_pred = 0.0

    savings = round(next_month_pred - total_cost, 2)

    return JsonResponse({
        "hourly": hourly_chart,
        "future": future,
        "new_anomalies": new_anoms,
        "top_anomalies": top_anoms,
        "top_recs": top_recs,
        "summary": {"total_cost": total_cost, "predicted_next_month": next_month_pred, "savings": savings}
    })


@login_required
def dashboard(request):
    hourly_path = ADVISOR_DIR / "billing_hourly.csv"
    if hourly_path.exists():
        df_hourly = pd.read_csv(hourly_path)
        df_hourly["timestamp"] = pd.to_datetime(df_hourly["timestamp"], errors="coerce")
        df_total = df_hourly.groupby("timestamp", as_index=False)["cost"].sum().sort_values("timestamp")
        last_points = df_total.tail(72)
        hourly_chart = [{"timestamp": t.strftime("%Y-%m-%d %H:%M"), "cost": float(c)} for t, c in zip(last_points["timestamp"], last_points["cost"])]
    else:
        hourly_chart = []

    anomalies = detect_hourly_anomalies()
    top_anomalies = sorted(anomalies, key=lambda x: x.get("timestamp", ""), reverse=True)[:3]
    recs = get_recommendations()
    top_recs = sorted(recs, key=lambda x: x.get("savings_value", 0), reverse=True)[:3]

    # summary (attempt train_and_forecast)
    next_month_pred = 0.0
    if train_and_forecast:
        try:
            fdf = train_and_forecast()
            next_month_pred = round(float(fdf.tail(30)["yhat"].sum()), 2)
        except Exception:
            next_month_pred = 0.0

    daily_path = ADVISOR_DIR / "billing_daily.csv"
    if daily_path.exists():
        df_daily = pd.read_csv(daily_path)
        total_cost = round(df_daily.tail(30)["total_cost"].sum(), 2) if not df_daily.empty else 0.0
    else:
        total_cost = 0.0

    summary = {"total_cost": total_cost, "change_percentage": 0.0, "predicted_next_month": next_month_pred, "savings": round(next_month_pred - total_cost, 2)}

    context = {
        "summary": summary,
        "hourly_chart_json": json.dumps(hourly_chart),
        "top_anomalies": top_anomalies,
        "top_recs": top_recs,
    }
    return render(request, "advisor/dashboard.html", context)


@login_required
def force_anomaly(request):
    # create an anomaly_flag file used in other logic (if you used file-based)
    (ADVISOR_DIR / "anomaly_flag.txt").write_text("1")
    # also append an immediate forced spike (so live_update picks it)
    append_one_live_hour(force=True)
    return redirect("advisor:dashboard")


@login_required
def solve_anomaly(request):
    flag = ADVISOR_DIR / "anomaly_flag.txt"
    if flag.exists():
        flag.unlink()
    return redirect("advisor:dashboard")


@login_required
def anomalies_list(request):
    anomalies = detect_hourly_anomalies()
    return render(request, "advisor/anomalies.html", {"anomalies": anomalies})


@login_required
def recommendations_list(request):
    recs = get_recommendations()
    return render(request, "advisor/recommendations.html", {"recs": recs})


@login_required
def profile_page(request):
    user = request.user
    if request.method == "POST":
        extra = request.POST.get("extra_emails", "").strip()
        emails = [e.strip() for e in extra.split(",") if e.strip()]
        write_extra_emails(user.username, emails)
        return redirect("advisor:profile")
    extras = read_extra_emails(user.username)
    return render(request, "advisor/profile.html", {"extras": extras})


def index(request):
    return render(request, "advisor/index.html")



def login_user(request):
    if request.method == "POST":
        uname = request.POST.get("username")
        pwd = request.POST.get("password")
        u = authenticate(request, username=uname, password=pwd)
        if u:
            login(request, u)
            return redirect("advisor:dashboard")
        else:
            return render(request, "advisor/login.html", {"error": "Invalid credentials"})
    return render(request, "advisor/login.html")


def logout_user(request):
    logout(request)
    return redirect("advisor:login")


def register_user(request):
    if request.method == "POST":
        username = request.POST.get("username") or ""
        email = request.POST.get("email") or ""
        password = request.POST.get("password") or ""
        password2 = request.POST.get("password2") or ""
        if not username:
            return render(request, "advisor/register.html", {"error": "Username required"})
        if password != password2:
            return render(request, "advisor/register.html", {"error": "Passwords do not match"})
        if User.objects.filter(username=username).exists():
            return render(request, "advisor/register.html", {"error": "Username exists"})
        u = User.objects.create_user(username=username, email=email, password=password)
        # profile will be created by signal
        login(request, u)
        return redirect("advisor:dashboard")
    return render(request, "advisor/register.html")
