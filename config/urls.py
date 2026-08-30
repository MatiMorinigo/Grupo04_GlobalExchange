from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.contrib.auth import logout
from django.shortcuts import redirect, render

def home(request):
    user = request.user
    if user.is_authenticated:
        return HttpResponse(f"""
            <h1>Global Exchange</h1>
            <p>Bienvenido, {user.email}</p>
            <form method="post" action="/logout/">
                <input type="hidden" name="csrfmiddlewaretoken" value="{request.META.get('CSRF_COOKIE', '')}">
                <button type="submit">Cerrar sesión</button>
            </form>
        """)
    return HttpResponse(f"""
        <h1>Global Exchange</h1>
        <p>No estás autenticado</p>
        <a href="/oidc/authenticate/">Iniciar sesión con Keycloak</a>
    """)

def custom_logout(request):
    logout(request)
    return redirect('http://localhost:8080/realms/global-exchange/protocol/openid-connect/logout?redirect_uri=http://localhost:8000')

def verificacion_fallida(request):
    return render(request, 'auth/verificacion_fallida.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('logout/', custom_logout, name='logout'),
    path('verificacion-fallida/', verificacion_fallida, name='verificacion_fallida'),
    path('', home, name='home'),
    path("api/", include("clientes.urls")),
]