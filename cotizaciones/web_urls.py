from django.urls import path

from .views import CotizacionWebListView


urlpatterns = [
    path("", CotizacionWebListView.as_view(), name="cotizacion-web-list"),
]
