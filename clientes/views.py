from rest_framework import generics

from .models import Cliente
from .serializers import ClienteSerializer
from rest_framework.exceptions import NotFound


class ClienteCreateView(generics.CreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

class ClienteListView(generics.ListAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer


class ClienteDetailView(generics.RetrieveUpdateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    lookup_field = "id_cliente"

    def get_object(self):
        try:
            return Cliente.objects.get(
                id_cliente=self.kwargs["id_cliente"]
            )
        except Cliente.DoesNotExist:
            raise NotFound("Cliente no encontrado.")