from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),

    # full list pages
    path("anomalies/", views.anomalies_list, name="anomalies_list"),
    path("recommendations/", views.recommendations_list, name="recommendations_list"),

    # anomaly controls
    path("force-anomaly/", views.force_anomaly, name="force_anomaly"),
    path("solve-anomaly/", views.solve_anomaly, name="solve_anomaly"),

    # Authentication
    
    path("login/", views.login_user, name="login"),
    path("register/", views.register_user, name="register"),
    path("logout/", views.logout_user, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_page, name="profile"),

]
