from django.urls import path

from .views import ClienteCreateView


urlpatterns = [
    path("clientes/", ClienteCreateView.as_view(), name="cliente-create"),
]