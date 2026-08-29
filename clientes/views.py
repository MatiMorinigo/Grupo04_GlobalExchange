from rest_framework import generics

from .models import Cliente
from .serializers import ClienteSerializer


class ClienteCreateView(generics.CreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer