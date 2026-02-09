"""
Logica de matching centralizada entre propiedades y clientes.
"""
import logging
from django.db.models import Q
from .models import Propiedad, Cliente

logger = logging.getLogger(__name__)


def buscar_clientes_para_propiedad(propiedad, agencia):
    """
    Busca clientes que hacen match con una propiedad dada.
    Si la propiedad no tiene zona asignada, no se puede hacer matching por zona.
    """
    # Si la propiedad no tiene zona, no podemos hacer matching geografico
    if not propiedad.zona:
        logger.debug(f"Propiedad {propiedad.ghl_contact_id} sin zona asignada, no se puede hacer matching.")
        return Cliente.objects.none()

    # Si la propiedad NO tiene algo, solo mostrar a clientes que NO lo requieran
    filtros_preferencias = []

    if propiedad.animales == Propiedad.Preferencias1.NO:
        filtros_preferencias.append(Q(animales=Cliente.Preferencias1.NO))

    if propiedad.balcon == Propiedad.Preferencias1.NO:
        filtros_preferencias.append(Q(balcon=Cliente.Preferencias2.IND))

    if propiedad.garaje == Propiedad.Preferencias1.NO:
        filtros_preferencias.append(Q(garaje=Cliente.Preferencias2.IND))

    if propiedad.patioInterior == Propiedad.Preferencias1.NO:
        filtros_preferencias.append(Q(patioInterior=Cliente.Preferencias2.IND))

    query = Q()
    for filtro in filtros_preferencias:
        query &= filtro

    clientes_match = Cliente.objects.filter(
        query,
        agencia=agencia,
        zona_interes=propiedad.zona,
        presupuesto_maximo__gte=propiedad.precio,
        habitaciones_minimas__lte=propiedad.habitaciones,
        metrosMinimo__lte=propiedad.metros
    ).distinct()

    logger.debug(f"Matching propiedad {propiedad.ghl_contact_id}: {clientes_match.count()} clientes encontrados")

    return clientes_match


def buscar_propiedades_para_cliente(cliente, agencia):
    """
    Busca propiedades que hacen match con un cliente dado.
    Si el cliente no tiene zonas de interes, busca en todas las zonas.
    """
    # Si el cliente REQUIERE algo (SI), la propiedad debe tenerlo
    filtros_preferencias = []

    if cliente.animales == Cliente.Preferencias1.SI:
        filtros_preferencias.append(Q(animales=Propiedad.Preferencias1.SI))

    if cliente.balcon == Cliente.Preferencias2.SI:
        filtros_preferencias.append(Q(balcon=Propiedad.Preferencias1.SI))

    if cliente.garaje == Cliente.Preferencias2.SI:
        filtros_preferencias.append(Q(garaje=Propiedad.Preferencias1.SI))

    if cliente.patioInterior == Cliente.Preferencias2.SI:
        filtros_preferencias.append(Q(patioInterior=Propiedad.Preferencias1.SI))

    query = Q()
    for filtro in filtros_preferencias:
        query &= filtro

    base_filter = {
        'agencia': agencia,
        'estado': Propiedad.estadoPiso.ACTIVO,
        'precio__lte': cliente.presupuesto_maximo,
        'habitaciones__gte': cliente.habitaciones_minimas,
        'metros__gte': cliente.metrosMinimo,
    }

    # Solo filtrar por zona si el cliente tiene zonas de interes
    zonas_interes = cliente.zona_interes.all()
    if zonas_interes.exists():
        base_filter['zona__in'] = zonas_interes

    propiedades_match = Propiedad.objects.filter(
        query,
        **base_filter
    ).distinct()

    logger.debug(f"Matching cliente {cliente.ghl_contact_id}: {propiedades_match.count()} propiedades encontradas")

    return propiedades_match


def actualizar_relaciones_propiedad(propiedad, clientes_match):
    """
    Actualiza las relaciones M2M entre propiedad y clientes.
    Usa .set() para reemplazar atomicamente en vez de clear() + add() uno a uno.
    """
    # .set() reemplaza todas las relaciones de golpe, es atomico y mas eficiente
    propiedad.interesados.set(clientes_match)
    return clientes_match.count()


def actualizar_relaciones_cliente(cliente, propiedades_match):
    """
    Actualiza las relaciones M2M entre cliente y propiedades.
    Usa .set() para reemplazar atomicamente en vez de clear() + add() uno a uno.
    """
    cliente.propiedades_interes.set(propiedades_match)
    return propiedades_match.count()
