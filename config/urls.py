from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.shortcuts import render

def home(request):
    user = request.user
    if user.is_authenticated:
        return HttpResponse(f"""
            <h1>Global Exchange</h1>
            <p>Bienvenido, {user.email}</p>
            <a href="/oidc/logout/">Cerrar sesión</a>
        """)
    return HttpResponse(f"""
        <h1>Global Exchange</h1>
        <p>No estás autenticado</p>
        <a href="/oidc/authenticate/">Iniciar sesión con Keycloak</a>
    """)



def verificacion_fallida(request):
    return render(request, 'auth/verificacion_fallida.html')


urlpatterns = [
    path("admin/", admin.site.urls),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('', home, name='home'),
    path("api/", include("clientes.urls")),
    path('verificacion-fallida/', verificacion_fallida, name='verificacion_fallida'),
]