from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from core.keycloak import tiene_rol
from clientes.models import Cliente

from .models import EstadoSolicitud, SolicitudAsociacion, UsuarioCliente


# ─────────────────────────────────────────────
# Mixin para administradores
# ─────────────────────────────────────────────

class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return tiene_rol(self.request, "administrador")


# ─────────────────────────────────────────────
# Vistas para usuarios normales
# ─────────────────────────────────────────────

class SolicitudBuscarClienteView(LoginRequiredMixin, View):
    """Busca un cliente por RUC (AJAX) y muestra el formulario de solicitud."""

    template_name = "usuarios/solicitud_buscar.html"

    def get(self, request):
        ruc = request.GET.get("ruc", "").strip()
        cliente = None
        ya_solicitado = False
        ya_aprobado = False

        if ruc:
            try:
                cliente = Cliente.objects.get(ruc=ruc, activo=True)
                ya_solicitado = SolicitudAsociacion.objects.filter(
                    usuario=request.user,
                    cliente=cliente,
                    estado=EstadoSolicitud.PENDIENTE,
                ).exists()
                ya_aprobado = SolicitudAsociacion.objects.filter(
                    usuario=request.user,
                    cliente=cliente,
                    estado=EstadoSolicitud.APROBADA,
                ).exists()
            except Cliente.DoesNotExist:
                cliente = None

            # Si es una petición AJAX retorna JSON
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                if cliente:
                    return JsonResponse({
                        "found": True,
                        "id_cliente": cliente.id_cliente,
                        "nombre": cliente.nombre,
                        "ruc": cliente.ruc,
                        "categoria": cliente.get_categoria_display(),
                        "tipo": cliente.get_tipo_display(),
                        "ya_solicitado": ya_solicitado,
                        "ya_aprobado": ya_aprobado,
                    })
                else:
                    return JsonResponse({"found": False})

        return render(request, self.template_name, {
            "active_menu": "solicitudes",
            "ruc": ruc,
            "cliente": cliente,
            "ya_solicitado": ya_solicitado,
            "ya_aprobado": ya_aprobado,
        })

    def post(self, request):
        id_cliente = request.POST.get("id_cliente")
        cliente = get_object_or_404(Cliente, id_cliente=id_cliente, activo=True)

        # Verificar que no exista ya una solicitud aprobada o pendiente
        existe_pendiente = SolicitudAsociacion.objects.filter(
            usuario=request.user,
            cliente=cliente,
            estado=EstadoSolicitud.PENDIENTE,
        ).exists()
        existe_aprobada = SolicitudAsociacion.objects.filter(
            usuario=request.user,
            cliente=cliente,
            estado=EstadoSolicitud.APROBADA,
        ).exists()

        if existe_pendiente:
            messages.warning(request, f"Ya tenés una solicitud pendiente para el cliente «{cliente.nombre}».")
        elif existe_aprobada:
            messages.info(request, f"Ya estás asociado al cliente «{cliente.nombre}».")
        else:
            SolicitudAsociacion.objects.create(
                usuario=request.user,
                cliente=cliente,
                estado=EstadoSolicitud.PENDIENTE,
            )
            messages.success(
                request,
                f"Solicitud enviada correctamente para el cliente «{cliente.nombre}». "
                "El administrador la revisará a la brevedad."
            )

        return redirect("mis-solicitudes")


class MisSolicitudesView(LoginRequiredMixin, ListView):
    """Lista las solicitudes propias del usuario autenticado."""

    template_name = "usuarios/mis_solicitudes.html"
    context_object_name = "solicitudes"

    def get_queryset(self):
        return SolicitudAsociacion.objects.filter(
            usuario=self.request.user
        ).select_related("cliente").order_by("-fecha_solicitud")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "solicitudes"
        return context


class ClienteActivoSeleccionarView(LoginRequiredMixin, View):
    """Permite al usuario cambiar su cliente activo."""

    def post(self, request):
        id_cliente = request.POST.get("id_cliente")
        cliente = get_object_or_404(Cliente, id_cliente=id_cliente, activo=True)

        # Verificar que el usuario tenga aprobada la asociación con este cliente
        tiene_aprobacion = SolicitudAsociacion.objects.filter(
            usuario=request.user,
            cliente=cliente,
            estado=EstadoSolicitud.APROBADA,
        ).exists()

        if not tiene_aprobacion:
            messages.error(request, "No tenés una asociación aprobada con ese cliente.")
            return redirect("home")

        perfil, _ = UsuarioCliente.objects.get_or_create(usuario=request.user)
        perfil.cliente_activo = cliente
        perfil.save(update_fields=["cliente_activo"])

        messages.success(request, f"Ahora estás operando con el cliente «{cliente.nombre}».")
        return redirect("home")


# ─────────────────────────────────────────────
# Vistas para administradores
# ─────────────────────────────────────────────

class SolicitudAdminListView(AdminRequiredMixin, ListView):
    """Panel del administrador: lista todas las solicitudes."""

    template_name = "usuarios/solicitud_admin_list.html"
    context_object_name = "solicitudes"
    paginate_by = 20

    def get_queryset(self):
        qs = SolicitudAsociacion.objects.select_related(
            "usuario", "cliente", "resuelto_por"
        ).order_by("-fecha_solicitud")

        estado = self.request.GET.get("estado", "PENDIENTE")
        if estado in EstadoSolicitud.values:
            qs = qs.filter(estado=estado)
        elif estado == "todas":
            pass  # sin filtro

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_menu"] = "admin_solicitudes"
        context["estado_filtro"] = self.request.GET.get("estado", "PENDIENTE")
        context["EstadoSolicitud"] = EstadoSolicitud
        context["total_pendientes"] = SolicitudAsociacion.objects.filter(
            estado=EstadoSolicitud.PENDIENTE
        ).count()
        return context


class SolicitudAdminAprobarView(AdminRequiredMixin, View):
    """Aprueba una solicitud de asociación."""

    def post(self, request, pk):
        solicitud = get_object_or_404(SolicitudAsociacion, pk=pk, estado=EstadoSolicitud.PENDIENTE)
        solicitud.estado = EstadoSolicitud.APROBADA
        solicitud.fecha_resolucion = timezone.now()
        solicitud.resuelto_por = request.user
        solicitud.save(update_fields=["estado", "fecha_resolucion", "resuelto_por"])

        # Si el usuario no tiene cliente activo asignado, asignarlo automáticamente
        perfil, _ = UsuarioCliente.objects.get_or_create(usuario=solicitud.usuario)
        if perfil.cliente_activo is None:
            perfil.cliente_activo = solicitud.cliente
            perfil.save(update_fields=["cliente_activo"])

        messages.success(
            request,
            f"Solicitud aprobada: {solicitud.usuario.get_full_name() or solicitud.usuario.username} "
            f"fue asociado a «{solicitud.cliente.nombre}»."
        )
        return redirect("admin-solicitudes")


class SolicitudAdminRechazarView(AdminRequiredMixin, View):
    """Rechaza una solicitud de asociación."""

    def post(self, request, pk):
        solicitud = get_object_or_404(SolicitudAsociacion, pk=pk, estado=EstadoSolicitud.PENDIENTE)
        solicitud.estado = EstadoSolicitud.RECHAZADA
        solicitud.fecha_resolucion = timezone.now()
        solicitud.resuelto_por = request.user
        solicitud.save(update_fields=["estado", "fecha_resolucion", "resuelto_por"])

        messages.warning(
            request,
            f"Solicitud rechazada: {solicitud.usuario.get_full_name() or solicitud.usuario.username} "
            f"— cliente «{solicitud.cliente.nombre}»."
        )
        return redirect("admin-solicitudes")
