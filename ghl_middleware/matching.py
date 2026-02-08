# ghl_middleware/matching.py
"""
CORRECCIÓN #27: Lógica de matching extraída de views.py para evitar duplicación.
Este módulo centraliza la lógica de búsqueda de coincidencias entre propiedades y clientes.
"""
import logging
from django.db.models import Q
from .models import Propiedad, Cliente

logger = logging.getLogger(__name__)


def buscar_clientes_para_propiedad(propiedad, agencia):
    """
    Busca clientes que hacen match con una propiedad dada.
    
    Criterios de matching:
    - Misma agencia
    - Zona de interés del cliente coincide con zona de la propiedad
    - Presupuesto máximo del cliente >= precio de la propiedad
    - Habitaciones mínimas del cliente <= habitaciones de la propiedad
    - Metros mínimos del cliente <= metros de la propiedad
    - Preferencias de animales/balcón/garaje/patio compatibles
    
    Args:
        propiedad: Instancia del modelo Propiedad
        agencia: Instancia del modelo Agencia
        
    Returns:
        QuerySet de clientes que hacen match
    """
    # Construir filtros de preferencias dinámicamente
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
    
    # Combinar filtros de preferencias (AND)
    query = Q()
    for filtro in filtros_preferencias:
        query &= filtro
    
    # Buscar clientes que cumplan todos los criterios
    clientes_match = Cliente.objects.filter(
        query,
        agencia=agencia,
        zona_interes=propiedad.zona,
        presupuesto_maximo__gte=propiedad.precio,
        habitaciones_minimas__lte=propiedad.habitaciones,
        metrosMinimo__lte=propiedad.metros
    ).distinct()
    
    logger.debug(f"🔍 Matching propiedad {propiedad.ghl_contact_id}: {clientes_match.count()} clientes encontrados")
    
    return clientes_match


def buscar_propiedades_para_cliente(cliente, agencia):
    """
    Busca propiedades que hacen match con un cliente dado.
    
    Criterios de matching:
    - Misma agencia
    - Propiedad activa
    - Zona de la propiedad está en zonas de interés del cliente
    - Precio <= presupuesto máximo del cliente
    - Habitaciones >= habitaciones mínimas del cliente
    - Metros >= metros mínimos del cliente
    - Preferencias de animales/balcón/garaje/patio compatibles
    
    Args:
        cliente: Instancia del modelo Cliente
        agencia: Instancia del modelo Agencia
        
    Returns:
        QuerySet de propiedades que hacen match
    """
    # Construir filtros de preferencias dinámicamente
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
    
    # Combinar filtros de preferencias (AND)
    query = Q()
    for filtro in filtros_preferencias:
        query &= filtro
    
    # Buscar propiedades que cumplan todos los criterios
    propiedades_match = Propiedad.objects.filter(
        query,
        agencia=agencia,
        estado=Propiedad.estadoPiso.ACTIVO,
        zona__in=cliente.zona_interes.all(),
        precio__lte=cliente.presupuesto_maximo,
        habitaciones__gte=cliente.habitaciones_minimas,
        metros__gte=cliente.metrosMinimo
    ).distinct()
    
    logger.debug(f"🔍 Matching cliente {cliente.ghl_contact_id}: {propiedades_match.count()} propiedades encontradas")
    
    return propiedades_match


def actualizar_relaciones_propiedad(propiedad, clientes_match):
    """
    Actualiza las relaciones many-to-many entre propiedad y clientes.
    
    Args:
        propiedad: Instancia del modelo Propiedad
        clientes_match: QuerySet de clientes que hacen match
    
    Returns:
        int: Número de matches
    """
    # Limpiar relaciones anteriores
    propiedad.interesados.clear()
    
    # Añadir nuevos matches
    for cliente in clientes_match:
        cliente.propiedades_interes.add(propiedad)
    
    return clientes_match.count()


def actualizar_relaciones_cliente(cliente, propiedades_match):
    """
    Actualiza las relaciones many-to-many entre cliente y propiedades.
    
    Args:
        cliente: Instancia del modelo Cliente
        propiedades_match: QuerySet de propiedades que hacen match
    
    Returns:
        int: Número de matches
    """
    # Limpiar relaciones anteriores
    cliente.propiedades_interes.clear()
    
    # Añadir nuevos matches
    for prop in propiedades_match:
        cliente.propiedades_interes.add(prop)
    
    return propiedades_match.count()
