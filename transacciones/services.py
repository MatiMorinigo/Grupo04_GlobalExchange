from decimal import Decimal

from django.db import IntegrityError
from django.db import transaction as db_transaction

from cotizaciones.models import ConfiguracionComision, TasaCambio
from cotizaciones.services import (
    SimulacionConversionError,
    obtener_beneficio_categoria,
    redondear_monto,
)
from integrations.proveedores_pago import (
    MetodoPagoNoHabilitadoError,
    ProveedorPagoError,
    get_proveedor,
)

from .models import (
    ESTADOS_PAGO_ACTIVOS,
    EstadoPago,
    EstadoTransaccion,
    Pago,
    TipoOperacion,
    Transaccion,
)



PYG = "PYG"
CIEN = Decimal("100")


class OperacionCambiariaError(ValueError):
    """Indica que una operación cambiaria no puede calcularse o registrarse."""
    pass


class PagoNoIniciableError(OperacionCambiariaError):
    """Indica que no puede iniciarse el pago de una transacción.

    El mensaje está pensado para mostrarse al cliente tal cual.
    """
    pass


MENSAJE_PAGO_EN_PROCESO = "Ya hay un pago en proceso para esta operación."


def obtener_tasa_vigente_compra(moneda_codigo):
    """Obtiene la tasa vigente del par entre una divisa y el guaraní.

    Solo considera tasas marcadas como vigentes cuyas dos monedas estén
    habilitadas, con el mismo criterio que utiliza el simulador de
    conversiones.

    Args:
        moneda_codigo (str): Código de la moneda extranjera de la operación.

    Returns:
        cotizaciones.models.TasaCambio: Tasa vigente del par divisa/PYG.

    Raises:
        OperacionCambiariaError: Si la moneda es el guaraní o si no existe
            una tasa vigente para el par requerido.
    """
    codigo = (moneda_codigo or "").upper()

    if codigo == PYG:
        raise OperacionCambiariaError("La operación debe involucrar una moneda extranjera.")

    tasa = (
        TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
        .filter(
            moneda_origen_id=codigo,
            moneda_destino_id=PYG,
            vigente=True,
            moneda_origen__activa=True,
            moneda_destino__activa=True,
        )
        .first()
    )

    if not tasa:
        raise OperacionCambiariaError(
            "No existe una cotización vigente para la moneda seleccionada."
        )

    return tasa


def calcular_compra(cliente, moneda_codigo, monto_divisa, tasa=None):
    """Calcula los importes de una compra de divisas para un cliente.

    El cliente entrega guaraníes y recibe la moneda extranjera indicada, por
    lo que se aplica el precio de venta de la cotización vigente. Sobre el
    subtotal se descuenta el beneficio correspondiente a la categoría del
    cliente, acotado por su límite configurado, y se suma la comisión de
    compra vigente en el sistema.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        moneda_codigo (str): Código de la moneda extranjera a comprar.
        monto_divisa (decimal.Decimal or str or int): Cantidad de divisa que
            el cliente desea adquirir.
        tasa (cotizaciones.models.TasaCambio or None): Tasa a utilizar. Si
            se omite, se busca la vigente para el par.

    Returns:
        dict: Importes y condiciones de la operación, con las claves que
        necesita el modelo Transaccion para registrarse.

    Raises:
        OperacionCambiariaError: Si el monto no es positivo, si no hay una
            cotización vigente o si la categoría del cliente no tiene
            configuración de beneficios.
    """
    monto = Decimal(str(monto_divisa))

    if monto <= 0:
        raise OperacionCambiariaError("El monto de la operación debe ser mayor a cero.")

    if tasa is None:
        tasa = obtener_tasa_vigente_compra(moneda_codigo)

    tasa_aplicada = tasa.precio_venta
    subtotal_pyg = redondear_monto(monto * tasa_aplicada)

    try:
        configuracion = obtener_beneficio_categoria(cliente.categoria_efectiva)
    except SimulacionConversionError as error:
        raise OperacionCambiariaError(str(error)) from error

    beneficio_porcentaje = Decimal("0.00")
    limite_beneficio_pyg = Decimal("0.00")

    if configuracion:
        beneficio_porcentaje = configuracion.porcentaje_beneficio
        limite_beneficio_pyg = configuracion.limite_mensual_pyg

    # Un límite en cero desactiva el beneficio, igual que en el simulador.
    if beneficio_porcentaje == 0 or limite_beneficio_pyg == 0:
        monto_beneficiado_pyg = Decimal("0.00")
        beneficio_monto_pyg = Decimal("0.00")
    else:
        monto_beneficiado_pyg = min(subtotal_pyg, limite_beneficio_pyg)
        beneficio_monto_pyg = redondear_monto(
            monto_beneficiado_pyg * beneficio_porcentaje / CIEN
        )

    comision_porcentaje = ConfiguracionComision.obtener().porcentaje_compra
    comision_monto_pyg = redondear_monto(subtotal_pyg * comision_porcentaje / CIEN)

    total_pyg = redondear_monto(subtotal_pyg - beneficio_monto_pyg + comision_monto_pyg)

    return {
        "tipo_operacion": TipoOperacion.COMPRA,
        "moneda": tasa.moneda_origen,
        "tasa_cambio": tasa,
        "tasa_aplicada": tasa_aplicada,
        "fecha_vigencia_tasa": tasa.fecha_vigencia,
        "monto_divisa": redondear_monto(monto),
        "subtotal_pyg": subtotal_pyg,
        "categoria_aplicada": cliente.categoria_efectiva,
        "beneficio_porcentaje": beneficio_porcentaje,
        "limite_beneficio_pyg": redondear_monto(limite_beneficio_pyg),
        "monto_beneficiado_pyg": redondear_monto(monto_beneficiado_pyg),
        "beneficio_monto_pyg": beneficio_monto_pyg,
        "comision_porcentaje": comision_porcentaje,
        "comision_monto_pyg": comision_monto_pyg,
        "total_pyg": total_pyg,
    }


def crear_transaccion_compra(
    cliente,
    usuario,
    moneda_codigo,
    monto_divisa,
    destino=None,
    metodo_pago=None,
    tasa=None,
):
    """Registra una compra de divisas en estado pendiente.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        usuario (django.contrib.auth.models.User): Usuario que la registra.
        moneda_codigo (str): Código de la moneda extranjera a comprar.
        monto_divisa (decimal.Decimal): Cantidad de divisa a adquirir.
        destino (destinos.models.DestinoAcreditacion or None): Destino donde
            se acreditará la divisa, si el cliente ya lo eligió.
        metodo_pago (pagos.models.MetodoPago or None): Medio con el que el
            cliente abonará la operación.
        tasa (cotizaciones.models.TasaCambio or None): Cotización a aplicar.
            Si se omite, se toma la vigente para el par.

    Returns:
        Transaccion: Transacción creada en estado pendiente.

    Raises:
        OperacionCambiariaError: Si los datos de la operación no permiten
            calcularla.
        django.core.exceptions.ValidationError: Si la transacción resultante
            no supera las validaciones del modelo.
    """
    with db_transaction.atomic():
        calculo = calcular_compra(cliente, moneda_codigo, monto_divisa, tasa=tasa)
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=usuario,
            destino_acreditacion=destino,
            metodo_pago=metodo_pago,
            **calculo,
        )
        transaccion.full_clean()
        transaccion.save()

    return transaccion


def obtener_tasa_vigente_venta(moneda_codigo):
    """Obtiene la tasa vigente del par entre una divisa y el guaraní para venta.

    Reutiliza la misma búsqueda que la compra: el par siempre es divisa→PYG.
    La distinción entre compra y venta se establece al seleccionar el precio
    (compra usa ``precio_venta``, venta usa ``precio_compra``).

    Args:
        moneda_codigo (str): Código de la moneda extranjera de la operación.

    Returns:
        cotizaciones.models.TasaCambio: Tasa vigente del par divisa/PYG.

    Raises:
        OperacionCambiariaError: Si la moneda es el guaraní o si no existe
            una tasa vigente para el par requerido.
    """
    return obtener_tasa_vigente_compra(moneda_codigo)


def calcular_venta(cliente, moneda_codigo, monto_divisa, tasa=None):
    """Calcula los importes de una venta de divisas para un cliente.

    El cliente entrega la moneda extranjera indicada y recibe guaraníes, por
    lo que se aplica el precio de compra de la cotización vigente. Sobre el
    subtotal se suma el beneficio correspondiente a la categoría del cliente,
    acotado por su límite configurado, y se descuenta la comisión de venta
    vigente en el sistema.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        moneda_codigo (str): Código de la moneda extranjera a vender.
        monto_divisa (decimal.Decimal or str or int): Cantidad de divisa que
            el cliente desea entregar.
        tasa (cotizaciones.models.TasaCambio or None): Tasa a utilizar. Si
            se omite, se busca la vigente para el par.

    Returns:
        dict: Importes y condiciones de la operación, con las claves que
        necesita el modelo Transaccion para registrarse.

    Raises:
        OperacionCambiariaError: Si el monto no es positivo, si no hay una
            cotización vigente o si la categoría del cliente no tiene
            configuración de beneficios.
    """
    monto = Decimal(str(monto_divisa))

    if monto <= 0:
        raise OperacionCambiariaError("El monto de la operación debe ser mayor a cero.")

    if tasa is None:
        tasa = obtener_tasa_vigente_venta(moneda_codigo)

    # En venta el cliente entrega divisas y recibe PYG: se aplica precio_compra.
    tasa_aplicada = tasa.precio_compra
    subtotal_pyg = redondear_monto(monto * tasa_aplicada)

    try:
        configuracion = obtener_beneficio_categoria(cliente.categoria_efectiva)
    except SimulacionConversionError as error:
        raise OperacionCambiariaError(str(error)) from error

    beneficio_porcentaje = Decimal("0.00")
    limite_beneficio_pyg = Decimal("0.00")

    if configuracion:
        beneficio_porcentaje = configuracion.porcentaje_beneficio
        limite_beneficio_pyg = configuracion.limite_mensual_pyg

    # Un límite en cero desactiva el beneficio, igual que en compra.
    if beneficio_porcentaje == 0 or limite_beneficio_pyg == 0:
        monto_beneficiado_pyg = Decimal("0.00")
        beneficio_monto_pyg = Decimal("0.00")
    else:
        monto_beneficiado_pyg = min(subtotal_pyg, limite_beneficio_pyg)
        beneficio_monto_pyg = redondear_monto(
            monto_beneficiado_pyg * beneficio_porcentaje / CIEN
        )

    # En venta: la comisión se descuenta de lo que recibe el cliente.
    comision_porcentaje = ConfiguracionComision.obtener().porcentaje_venta
    comision_monto_pyg = redondear_monto(subtotal_pyg * comision_porcentaje / CIEN)

    # Cliente recibe: subtotal + beneficio - comision
    total_pyg = redondear_monto(subtotal_pyg + beneficio_monto_pyg - comision_monto_pyg)

    return {
        "tipo_operacion": TipoOperacion.VENTA,
        "moneda": tasa.moneda_origen,
        "tasa_cambio": tasa,
        "tasa_aplicada": tasa_aplicada,
        "fecha_vigencia_tasa": tasa.fecha_vigencia,
        "monto_divisa": redondear_monto(monto),
        "subtotal_pyg": subtotal_pyg,
        "categoria_aplicada": cliente.categoria_efectiva,
        "beneficio_porcentaje": beneficio_porcentaje,
        "limite_beneficio_pyg": redondear_monto(limite_beneficio_pyg),
        "monto_beneficiado_pyg": redondear_monto(monto_beneficiado_pyg),
        "beneficio_monto_pyg": beneficio_monto_pyg,
        "comision_porcentaje": comision_porcentaje,
        "comision_monto_pyg": comision_monto_pyg,
        "total_pyg": total_pyg,
    }


def crear_transaccion_venta(
    cliente,
    usuario,
    moneda_codigo,
    monto_divisa,
    destino=None,
    metodo_pago=None,
    tasa=None,
):
    """Registra una venta de divisas en estado pendiente.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        usuario (django.contrib.auth.models.User): Usuario que la registra.
        moneda_codigo (str): Código de la moneda extranjera a vender.
        monto_divisa (decimal.Decimal): Cantidad de divisa que el cliente entrega.
        destino (destinos.models.DestinoAcreditacion or None): Destino donde
            se acreditará la divisa, si el cliente ya lo eligió.
        metodo_pago (pagos.models.MetodoPago or None): Medio con el que el
            cliente realizará la operación.
        tasa (cotizaciones.models.TasaCambio or None): Cotización a aplicar.
            Si se omite, se toma la vigente para el par.

    Returns:
        Transaccion: Transacción creada en estado pendiente.

    Raises:
        OperacionCambiariaError: Si los datos de la operación no permiten
            calcularla.
        django.core.exceptions.ValidationError: Si la transacción resultante
            no supera las validaciones del modelo.
    """
    with db_transaction.atomic():
        calculo = calcular_venta(cliente, moneda_codigo, monto_divisa, tasa=tasa)
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=usuario,
            destino_acreditacion=destino,
            metodo_pago=metodo_pago,
            **calculo,
        )
        transaccion.full_clean()
        transaccion.save()

    return transaccion


def importe_a_cobrar(transaccion):
    """Determina el importe y la moneda que el cliente paga en una operación.

    En una compra el cliente paga el total en guaraníes; en una venta entrega
    la divisa que vende.

    Args:
        transaccion (Transaccion): Operación a pagar.

    Returns:
        tuple[decimal.Decimal, str]: Importe y código de la moneda a cobrar.
    """
    if transaccion.tipo_operacion == TipoOperacion.COMPRA:
        return transaccion.total_pyg, PYG
    return transaccion.monto_divisa, transaccion.moneda_id


def metodo_permite_pagar(transaccion):
    """Indica si el método de pago actual de la operación permite iniciar el pago.

    Aplica las mismas comprobaciones previas que ``iniciar_pago`` sin crear
    ningún pago ni contactar al proveedor.

    Args:
        transaccion (Transaccion): Operación a pagar.

    Returns:
        bool: False si la operación no tiene método, si está inactivo, si no
        es del cliente o si el proveedor no lo habilita para este importe.
    """
    metodo = transaccion.metodo_pago
    if metodo is None or not metodo.activo or metodo.cliente_id != transaccion.cliente_id:
        return False
    monto, moneda = importe_a_cobrar(transaccion)
    try:
        get_proveedor(metodo).validar(metodo, monto, moneda)
    except MetodoPagoNoHabilitadoError:
        return False
    return True


def iniciar_pago(transaccion, usuario, metodo_pago=None):
    """Inicia el pago de una transacción pendiente ante el proveedor externo.

    El proceso tiene dos fases. Primero, con la transacción bloqueada, valida
    que esté pendiente, que no tenga otro pago en curso y que su método de
    pago esté habilitado para el proveedor, y registra el pago como
    ``INICIADO``. Después, fuera de la transacción de base de datos, envía la
    solicitud al proveedor y guarda su respuesta. Iniciar el pago nunca
    modifica el estado de la transacción: la confirmación llega más tarde.

    Si se indica un método de pago distinto del de la operación (por ejemplo,
    después de que el proveedor rechazó la tarjeta), pasa a ser el método de la
    operación siempre que el pago pueda iniciarse. Los intentos anteriores
    conservan el método con el que se hicieron.

    Args:
        transaccion (Transaccion): Operación a pagar.
        usuario (django.contrib.auth.models.User): Usuario que inicia el pago.
        metodo_pago (pagos.models.MetodoPago or None): Método con el que se
            quiere pagar. Si se omite, se usa el de la operación.

    Returns:
        Pago: Pago ``EN_PROCESO`` con la referencia externa del proveedor.

    Raises:
        PagoNoIniciableError: Si la transacción no está pendiente, ya tiene
            un pago en curso, el método elegido no es un método activo del
            cliente, su método de pago no está habilitado o el proveedor
            rechazó o no pudo procesar la solicitud. En los dos últimos casos
            el pago queda registrado como ``RECHAZADO`` o ``ERROR``.
    """
    try:
        with db_transaction.atomic():
            transaccion = (
                # Solo se bloquea la transacción: PostgreSQL no admite FOR UPDATE
                # sobre el método de pago, que es el lado nulable del JOIN.
                Transaccion.objects.select_for_update(of=("self",))
                .select_related("metodo_pago")
                .get(pk=transaccion.pk)
            )
            if transaccion.estado != EstadoTransaccion.PENDIENTE:
                raise PagoNoIniciableError(
                    "Solo se pueden pagar operaciones en estado pendiente."
                )
            if transaccion.pagos.filter(estado__in=ESTADOS_PAGO_ACTIVOS).exists():
                raise PagoNoIniciableError(MENSAJE_PAGO_EN_PROCESO)

            if metodo_pago is not None and metodo_pago.pk != transaccion.metodo_pago_id:
                if not metodo_pago.activo or metodo_pago.cliente_id != transaccion.cliente_id:
                    raise PagoNoIniciableError(
                        "El método de pago seleccionado no está disponible."
                    )
                transaccion.metodo_pago = metodo_pago
                transaccion.save(update_fields=["metodo_pago", "actualizada_en"])

            metodo = transaccion.metodo_pago
            if metodo is None or not metodo.activo or metodo.cliente_id != transaccion.cliente_id:
                raise PagoNoIniciableError(
                    "La operación no tiene un método de pago activo para realizar el pago."
                )

            monto, moneda = importe_a_cobrar(transaccion)
            try:
                proveedor = get_proveedor(metodo)
                proveedor.validar(metodo, monto, moneda)
            except MetodoPagoNoHabilitadoError as error:
                raise PagoNoIniciableError(str(error)) from error

            pago = Pago.objects.create(
                transaccion=transaccion,
                metodo_pago=metodo,
                proveedor=proveedor.codigo,
                monto=proveedor.monto_a_cobrar(monto, moneda),
                moneda_id=moneda,
                iniciado_por=usuario,
            )
    except IntegrityError as error:
        # Otra solicitud registró un pago activo en paralelo.
        raise PagoNoIniciableError(MENSAJE_PAGO_EN_PROCESO) from error

    try:
        resultado = proveedor.iniciar_pago(pago)
    except ProveedorPagoError as error:
        pago.estado = EstadoPago.RECHAZADO if error.rechazado else EstadoPago.ERROR
        pago.referencia_externa = error.referencia_externa or None
        pago.mensaje_proveedor = error.detalle or error.mensaje_usuario
        pago.save(update_fields=["estado", "referencia_externa", "mensaje_proveedor", "actualizado_en"])
        raise PagoNoIniciableError(error.mensaje_usuario) from error

    pago.estado = EstadoPago.EN_PROCESO
    pago.referencia_externa = resultado.referencia_externa
    pago.save(update_fields=["estado", "referencia_externa", "actualizado_en"])
    return pago
