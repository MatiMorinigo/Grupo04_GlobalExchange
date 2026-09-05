from django.contrib import admin
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.urls import include, path

from core import views as core_views


def custom_logout(request):
    logout(request)
    return redirect(
        "http://localhost:8080/realms/global-exchange/protocol/openid-connect/logout"
        "?redirect_uri=http://localhost:8000"
    )


def verificacion_fallida(request):
    return render(request, "auth/verificacion_fallida.html")


urlpatterns = [
    path("", core_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("clientes/", include("clientes.web_urls")),
    path("cotizaciones/", include("cotizaciones.web_urls")),
    path("api/", include("clientes.urls")),
    path("api/cotizaciones/", include("cotizaciones.urls")),
    path("usuarios/", include("usuarios.web_urls")),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("logout/", custom_logout, name="logout"),
    path("verificacion-fallida/", verificacion_fallida, name="verificacion_fallida"),
]
