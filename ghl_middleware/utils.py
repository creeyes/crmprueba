# ghl_middleware/utils.py
"""
CORRECCIONES:
- #18: Implementado backoff exponencial en vez de time.sleep hardcodeados
- #19: HTTPAdapter con reintentos automáticos para errores 500 y timeouts
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import time
import random
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.db import transaction
from .models import GHLToken


# Configuración del logger estándar de Django
logger = logging.getLogger(__name__)


# --- CORRECCIÓN #19: Sesión HTTP con reintentos automáticos ---
def create_resilient_session():
    """
    Crea una sesión HTTP con reintentos automáticos para errores transitorios.
    - Reintenta en errores 500, 502, 503, 504
    - Backoff exponencial entre reintentos
    - Máximo 3 reintentos
    """
    session = requests.Session()
    
    retry_strategy = Retry(
        total=3,  # Número total de reintentos
        backoff_factor=1,  # Espera 1s, 2s, 4s entre reintentos
        status_forcelist=[429, 500, 502, 503, 504],  # Códigos HTTP a reintentar
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS"],
        raise_on_status=False,  # No lanzar excepción, manejar manualmente
        respect_retry_after_header=True,  # CORRECCIÓN #18: Leer Retry-After de GHL
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


# Sesión global reutilizable (más eficiente que crear nuevas conexiones)
_http_session = create_resilient_session()


# --- CORRECCIÓN #18: Función de backoff exponencial ---
def exponential_backoff(attempt, base_delay=0.2, max_delay=10.0, jitter=True):
    """
    Calcula el tiempo de espera con backoff exponencial.
    - attempt: número del intento (0, 1, 2, ...)
    - base_delay: delay base en segundos
    - max_delay: delay máximo
    - jitter: añade variación aleatoria para evitar thundering herd
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random())  # Jitter de ±50%
    return delay


def rate_limit_wait(response=None, default_wait=0.2):
    """
    CORRECCIÓN #18: Espera inteligente basada en headers de rate limiting.
    Lee Retry-After si está presente, si no usa backoff.
    """
    if response is not None:
        # Verificar si GHL nos dice cuánto esperar
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                wait_time = int(retry_after)
                logger.info(f"⏳ Rate limited. Esperando {wait_time}s (Retry-After header)")
                time.sleep(wait_time)
                return
            except ValueError:
                pass
        
        # Si recibimos 429 sin Retry-After, esperar más
        if response.status_code == 429:
            wait_time = exponential_backoff(attempt=2)  # Más agresivo
            logger.warning(f"⚠️ Rate limited (429). Esperando {wait_time:.2f}s")
            time.sleep(wait_time)
            return
    
    # Delay por defecto (pequeño para no ralentizar demasiado)
    time.sleep(default_wait)


# --- FUNCIONES PARA TOKEN AUTO-REFRESH CON LOCKING ---

def get_valid_token(location_id):
    """
    Recupera el token asegurando exclusividad en el acceso a la base de datos.
    Usa 'select_for_update' para evitar que dos procesos refresquen al mismo tiempo (Race Condition).
    """
    try:
        # Iniciamos transacción para bloquear la fila hasta que terminemos
        with transaction.atomic():
            try:
                # select_for_update() detiene a otros procesos aquí si ya hay uno trabajando con este location_id
                token_obj = GHLToken.objects.select_for_update().get(location_id=location_id)
            except GHLToken.DoesNotExist:
                logger.error(f"❌ No se encontró token para location_id: {location_id}")
                return None

            # Calculamos cuándo caduca (updated_at + expires_in)
            # Margen de seguridad: 10 minutos (600 segundos)
            expiration_time = token_obj.updated_at + timedelta(seconds=token_obj.expires_in - 600)
            
            # Si el token ha caducado, lo refrescamos DENTRO del bloqueo.
            # El siguiente proceso que entre verá el token ya actualizado.
            if timezone.now() > expiration_time:
                logger.info(f"🔄 El token de {location_id} ha caducado. Refrescando bajo bloqueo DB...")
                return refresh_ghl_token(token_obj)
            
            return token_obj.access_token

    except Exception as e:
        # Captura genérica para asegurar que cualquier fallo no rompa el flujo sin loguear
        logger.error(f"❌ Error crítico obteniendo token seguro: {str(e)}", exc_info=True)
        return None


def refresh_ghl_token(token_obj):
    """
    Solicita un nuevo access_token a GHL usando el refresh_token guardado.
    NOTA: Esta función se ejecuta dentro del lock de get_valid_token.
    CORRECCIÓN #19: Usa sesión con reintentos automáticos.
    """
    url = "https://services.leadconnectorhq.com/oauth/token"
    payload = {
        'client_id': settings.GHL_CLIENT_ID,
        'client_secret': settings.GHL_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': token_obj.refresh_token,
        'user_type': 'Location'
    }
    
    try:
        # Timeout estricto para no mantener la DB bloqueada demasiado tiempo si GHL cae
        response = _http_session.post(url, data=payload, timeout=20)
        new_data = response.json()
        
        if response.status_code == 200:
            token_obj.access_token = new_data.get('access_token')
            token_obj.refresh_token = new_data.get('refresh_token')
            token_obj.expires_in = new_data.get('expires_in', 86400)
            token_obj.save()  # Esto confirma la transacción en get_valid_token
            logger.info(f"✅ Token refrescado correctamente para {token_obj.location_id}")
            return token_obj.access_token
        else:
            logger.error(f"❌ Error refrescando token GHL: {new_data}")
            return None
    except Exception as e:
        logger.error(f"❌ Excepción al refrescar token: {str(e)}")
        return None


# --- FUNCIONES DE API GHL (Asociaciones) ---

def ghl_get_current_associations(access_token, location_id, property_id):
    """
    Obtiene las asociaciones actuales de una propiedad.
    CORRECCIONES #18 y #19: Backoff inteligente y reintentos automáticos.
    """
    rate_limit_wait()  # CORRECCIÓN #18: Backoff inteligente
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Accept": "application/json"
    }
    
    url = f"https://services.leadconnectorhq.com/associations/relations/{property_id}"
    params = {"locationId": location_id}
    found_relations_map = {}

    try:
        response = _http_session.get(url, headers=headers, params=params, timeout=10)
        
        # CORRECCIÓN #18: Manejar rate limiting
        rate_limit_wait(response, default_wait=0)
        
        if response.status_code == 200:
            data = response.json()
            relations_list = data.get('relations', [])
            
            for rel in relations_list:
                r1 = rel.get('firstRecordId')
                r2 = rel.get('secondRecordId')
                
                # Identificamos contacto (el que NO es la propiedad)
                contact_id = r2 if r1 == property_id else r1
                
                if contact_id:
                    found_relations_map[contact_id] = rel
            
            return found_relations_map
        elif response.status_code == 404:
            return {}
        else:
            logger.error(f"⚠️ Error GHL GET Associations: {response.status_code}")
            return {}
    except Exception as e:
        logger.error(f"❌ Excepción GET Associations: {str(e)}")
        return {}


def ghl_delete_association(access_token, location_id, relation_id):
    """
    Elimina una asociación en GHL.
    CORRECCIONES #18 y #19: Backoff inteligente y reintentos automáticos.
    """
    rate_limit_wait()  # CORRECCIÓN #18
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    url = f"https://services.leadconnectorhq.com/associations/relations/{relation_id}"
    params = {"locationId": location_id}

    try:
        response = _http_session.delete(url, headers=headers, params=params, timeout=10)
        rate_limit_wait(response, default_wait=0)
        return response.status_code in [200, 204]
    except Exception as e:
        logger.error(f"❌ Excepción DELETE Association: {str(e)}")
        return False


def ghl_associate_records(access_token, location_id, property_id, contact_id, association_id):
    """
    Crea una asociación entre propiedad y contacto.
    CORRECCIONES #18 y #19: Backoff inteligente y reintentos automáticos.
    """
    rate_limit_wait()  # CORRECCIÓN #18
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    url = "https://services.leadconnectorhq.com/associations/relations"
    
    payload = {
        "locationId": location_id,
        "associationId": association_id, 
        "firstRecordId": contact_id,  
        "secondRecordId": property_id 
    }

    try:
        response = _http_session.post(url, json=payload, headers=headers, timeout=10)
        rate_limit_wait(response, default_wait=0)
        return response.status_code in [200, 201]
    except Exception as e:
        logger.error(f"❌ Error asociando registros {contact_id}-{property_id}: {str(e)}")
        return False


# --- AUTO-DETECCIÓN INTELIGENTE ---
def get_association_type_id(access_token, location_id, object_key="propiedad"):
    """
    Busca el ID de asociación entre Contacto y el Custom Object.
    CORRECCIÓN #19: Usa sesión con reintentos.
    """
    url = "https://services.leadconnectorhq.com/associations/types"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Accept": "application/json"
    }
    
    try:
        response = _http_session.get(url, headers=headers, params={"locationId": location_id}, timeout=10)
        
        if response.status_code == 200:
            types = response.json().get('associationTypes', [])
            
            target_singular = object_key.lower()
            
            logger.info(f"🕵️ Buscando asociación para '{target_singular}' en {location_id}...")

            for t in types:
                keys_found = [
                    t.get('firstObjectKey', ''),
                    t.get('secondObjectKey', ''),
                    t.get('sourceKey', ''),
                    t.get('targetKey', '')
                ]
                keys_found = [k.lower() for k in keys_found if k]
                
                is_contact = 'contact' in keys_found
                is_target = any((target_singular in k) for k in keys_found)
                
                if is_contact and is_target:
                    found_id = t['id']
                    logger.info(f"✅ ID Encontrado: {found_id}")
                    return found_id
            
            logger.warning(f"⚠️ No se encontró ninguna asociación compatible con '{object_key}'")
            return None
            
        else:
            logger.error(f"❌ Error API GHL al buscar ID ({response.status_code}): {response.text}")
            return None

    except Exception as e:
        logger.error(f"❌ Excepción buscando Association ID: {str(e)}")
        return None


def ghlActualizarZonaAPI(locationId, opciones, token, url, prop):
    """
    Actualiza las opciones de zona en un campo personalizado de GHL.
    CORRECCIÓN #19: Usa sesión con reintentos.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    logger.debug(f'Update Options Payload: {opciones}')
    
    try:
        payload = {"options": opciones}
        if prop:
            payload["locationId"] = locationId
            payload["showInForms"] = True
            
        response = _http_session.put(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            logger.info("✅ Actualización exitosa de zonas en GHL")
            return response.json() if response.text else True
        else:
            logger.error(f"❌ Error actualizando zonas {response.status_code}: {response.text}")
            return None

    except Exception as e:
        logger.error(f"💥 Error de conexión actualizando zonas: {str(e)}")
        return None