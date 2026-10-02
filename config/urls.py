from django.contrib import admin
from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.urls import include, path

from core import views as core_views


def custom_logout(request):
    """Cierra la sesión local y redirige al cierre de sesión de Keycloak.

    Args:
        request (django.http.HttpRequest): Solicitud cuya sesión se cerrará.

    Returns:
        django.http.HttpResponseRedirect: Redirección al endpoint de Keycloak
        en localhost:8080, con retorno indicado a localhost:8000.
    """
    logout(request)
    return redirect(
        "http://localhost:8080/realms/global-exchange/protocol/openid-connect/logout"
        "?redirect_uri=http://localhost:8000"
    )


def verificacion_fallida(request):
    """Muestra la página de verificación fallida.

    Args:
        request (django.http.HttpRequest): Solicitud recibida por la vista.

    Returns:
        django.http.HttpResponse: Página de error de verificación.
    """
    return render(request, "auth/verificacion_fallida.html")


urlpatterns = [
    path("", core_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("clientes/", include("clientes.web_urls")),
    path("cotizaciones/", include("cotizaciones.web_urls")),
    path("destinos-acreditacion/", include("destinos.web_urls")),
    path("metodos-pago/", include("pagos.web_urls")),
    path("transacciones/", include("transacciones.web_urls")),
    path("api/", include("clientes.urls")),
    path("api/cotizaciones/", include("cotizaciones.urls")),
    path("api/pagos/", include("pagos.urls")),
    path("usuarios/", include("usuarios.web_urls")),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("logout/", custom_logout, name="logout"),
    path("verificacion-fallida/", verificacion_fallida, name="verificacion_fallida"),
]
