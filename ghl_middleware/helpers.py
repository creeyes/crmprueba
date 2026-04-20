# ghl_middleware/helpers.py
"""
CORRECCIÓN #28: Helpers movidos desde views.py para mejor organización.
Funciones de utilidad para procesamiento de datos de webhooks.
"""
from .models import Cliente, Propiedad


def clean_currency(value):
    """
    Este debug es muy simple y sencillo. SOLO SOPORTA EUROS Y DOLARES
    """
    if not value:
        return 0.0
    simbolo = value[0]
    cuerpo = value[1:].strip()

    if simbolo == "$":
        resultado = cuerpo.replace(",", "")
        
    elif simbolo == "€":
        resultado = cuerpo.replace(".", "").replace(",", ".")
        
    else:
        raise ValueError(f"MONEDA NO SOPORTADA: '{simbolo}'. Añade un 'elif' para ella.")

    return float(resultado)


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
    Traduce el estado de la propiedad desde GHL o desde Frontend React al enum del modelo.
    """
    mapa = {
        "vendido": Propiedad.estadoPiso.VENDIDO,
        "a la venta": Propiedad.estadoPiso.ACTIVO,
        "no es oficial": Propiedad.estadoPiso.NoOficial,
        "activo": Propiedad.estadoPiso.ACTIVO,
        "inactivo": Propiedad.estadoPiso.NoOficial,
        "alquilado": Propiedad.estadoPiso.NoOficial, # mapeos de fallback para react
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


def parse_zona_nombres(zona_input):
    """
    Parsea las zonas desde string o lista. Limpia el sufijo '--'.
    Retorna una lista de nombres de zonas limpios.
    """
    if not zona_input:
        return []
    
    if isinstance(zona_input, list):
        zona_bruta = [str(z).strip() for z in zona_input]
    else:
        zona_bruta = [z.strip() for z in str(zona_input).split(",")]
        
    z_nombres = [z.split("--")[0].strip() for z in zona_bruta if z.split("--")[0].strip()]
    return z_nombres


def parse_property_data(data, custom_data=None):
    """
    Unifica el saneamiento de datos de la Propiedad, sirviendo tanto para Webhooks 
    (que traen 'custom_data') como para peticiones del Frontend (que solo traen 'data').
    """
    if custom_data is None:
        custom_data = {}
        
    estado_base = estadoPropTrad(custom_data.get("estado") or data.get("estado"))
    
    # Soporta imagenes como lista pura de strings (Frontend) o como diccionarios de GHL (Webhook)
    imagenes_brutas = custom_data.get('imagenesUrl') or data.get('imagenesUrl')
    if isinstance(imagenes_brutas, list) and len(imagenes_brutas) > 0 and isinstance(imagenes_brutas[0], str):
        imagenes_limpias = imagenes_brutas
    else:
        imagenes_limpias = guardadorURL(imagenes_brutas)

    parsed_data = {
        'precio': clean_currency(custom_data.get('precio') or data.get('precio')),
        'habitaciones': clean_int(custom_data.get('habitaciones') or data.get('habitaciones')),
        'estado': estado_base,
        'animales': preferenciasTraductor1(custom_data.get('animales') or data.get('animales')),
        'metros': clean_int(custom_data.get('metros') or data.get('metros')),
        'balcon': preferenciasTraductor1(custom_data.get('balcon') or data.get('balcon')),
        'garaje': preferenciasTraductor1(custom_data.get('garaje') or data.get('garaje')),
        'patioInterior': preferenciasTraductor1(custom_data.get('patioInterior') or data.get('patioInterior')),
        'descripcion': (custom_data.get('descripcion') or data.get('descripcion') or "").strip(),
        'calle': (custom_data.get('calle') or data.get('calle') or "").strip(),
        'notas': (custom_data.get('notas') or data.get('notas') or "").strip(),
        'favorito': bool(custom_data.get('favorito') or data.get('favorito')),
        'imagenesUrl': imagenes_limpias,
    }
    return parsed_data



# --- FUNCIONES INVERSAS (DB → GHL) ---

def format_currency_eur(value):
    """
    Formatea un Decimal/float como moneda EUR para GHL.
    Inverso de clean_currency().
    Ej: 150000.50 → "€150.000,50"
    """
    if not value:
        return "€0,00"
    # Formatear con separadores
    formatted = f"{float(value):,.2f}"
    # Convertir de formato ingles (1,234.56) a formato EUR (1.234,56)
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€{formatted}"


def preferencias_inversa_1(value):
    """
    Inverso de preferenciasTraductor1().
    Convierte el valor del enum del modelo al formato que espera GHL.
    'si' → 'Si', 'no' → 'No'
    """
    mapa = {"si": "Si", "no": "No"}
    return mapa.get(value, "No")


def preferencias_inversa_2(value):
    """
    Inverso de preferenciasTraductor2().
    'si' → 'Si', 'ind' → 'Indiferente'
    """
    mapa = {"si": "Si", "ind": "Indiferente"}
    return mapa.get(value, "Indiferente")


def estado_prop_inversa(value):
    """
    Inverso de estadoPropTrad().
    'activo' → 'a_la_venta', 'vendido' → 'vendido', 'noficial' → 'no_es_oficial'
    """
    mapa = {
        "activo": "a_la_venta",
        "vendido": "vendido",
        "noficial": "no_es_oficial",
    }
    return mapa.get(value, "no_es_oficial")


def imagenes_para_ghl(urls_list):
    """
    Inverso de guardadorURL().
    Convierte lista de URLs a formato GHL: [{"url": "..."}]
    """
    if not urls_list:
        return []
    return [{"url": url} for url in urls_list if url]
