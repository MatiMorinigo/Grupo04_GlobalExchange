from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

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

urlpatterns = [
    path('admin/', admin.site.urls),
    path('oidc/', include('mozilla_django_oidc.urls')),
    path('', home, name='home'),
]