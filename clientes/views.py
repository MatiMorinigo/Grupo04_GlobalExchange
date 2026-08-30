from rest_framework import generics,status
from .models import Cliente
from .serializers import ClienteSerializer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound
from .permissions import EsAdministrador

class ClienteCreateView(generics.CreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]


class ClienteListView(generics.ListAPIView):
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]

    def get_queryset(self):
        queryset = Cliente.objects.all()

        categoria = self.request.query_params.get("categoria")
        tipo = self.request.query_params.get("tipo")
        activo = self.request.query_params.get("activo")

        if categoria:
            queryset = queryset.filter(categoria=categoria)

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if activo is not None:
            queryset = queryset.filter(
                activo=activo.lower() == "true"
            )

        return queryset

class ClienteDetailView(generics.RetrieveUpdateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [EsAdministrador]
    lookup_field = "id_cliente"
    def get_object(self):
        try:
            return Cliente.objects.get(
                id_cliente=self.kwargs["id_cliente"]
            )
        except Cliente.DoesNotExist:
            raise NotFound("Cliente no encontrado.")

class ClienteDeactivateView(APIView):
    permission_classes = [EsAdministrador]
    def patch(self, request, id_cliente):
        try:
            cliente = Cliente.objects.get(id_cliente=id_cliente)
        except Cliente.DoesNotExist:
            raise NotFound("Cliente no encontrado.")

        if not cliente.activo:
            return Response(
                {"detail": "El cliente ya se encuentra inactivo."},
                status=status.HTTP_400_BAD_REQUEST
            )

        cliente.activo = False
        cliente.save(update_fields=["activo"])

        return Response(
            {"detail": "Cliente desactivado correctamente."},
            status=status.HTTP_200_OK
        )