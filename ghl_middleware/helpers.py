# ghl_middleware/helpers.py
"""
CORRECCIÓN #28: Helpers movidos desde views.py para mejor organización.
Funciones de utilidad para procesamiento de datos de webhooks.
"""
from .models import Cliente, Propiedad


def clean_currency(value):
    """
    Limpia y convierte un valor de moneda a float.
    Maneja formatos como '$1234,56' o '1234,56'.
    """
    if not value:
        return 0.0
    try:
        return float(str(value).replace("€","").replace('$', '').replace(',', '.').strip())
    except ValueError:
        return 0.0


def clean_int(value):
    """
    Limpia y convierte un valor a integer.
    Maneja valores con decimales como '3.0'.
    """
    if not value:
        return 0
    try:
        return int(float(str(value)))
    except ValueError:
        return 0


def preferenciasTraductor1(value):
    """
    Traduce valores de preferencias tipo 1 (Si/No) al enum del modelo.
    Usado para campos binarios como 'animales'.
    """
    mapa = {
        "si": Cliente.Preferencias1.SI,
        "no": Cliente.Preferencias1.NO,
    }
    value = (value or "").lower()
    return mapa.get(value, Cliente.Preferencias1.NO)


def preferenciasTraductor2(value):
    """
    Traduce valores de preferencias tipo 2 (Si/Indiferente) al enum del modelo.
    Usado para campos como 'balcon', 'garaje', 'patioInterior'.
    """
    mapa = {
        "si": Cliente.Preferencias2.SI,
        "indiferente": Cliente.Preferencias2.IND
    }
    value = str(value or "").lower()
    return mapa.get(value, Cliente.Preferencias2.IND)


def estadoPropTrad(value):
    """
    Traduce el estado de la propiedad desde GHL al enum del modelo.
    """
    mapa = {
        "vendido": Propiedad.estadoPiso.VENDIDO,
        "a la venta": Propiedad.estadoPiso.ACTIVO,
        "no es oficial": Propiedad.estadoPiso.NoOficial
    }
    value = str(value or "").replace("_", " ").lower()
    return mapa.get(value, Propiedad.estadoPiso.NoOficial)


def guardadorURL(value):
    """
    Extrae las URLs de imágenes desde la estructura de datos de GHL.
    Espera una lista de dicts con clave 'url'.
    """
    lista = []
    if value and value != "null":
        if isinstance(value, list):
            lista = [data.get('url') for data in value if isinstance(data, dict) and data.get('url')]
    return lista
