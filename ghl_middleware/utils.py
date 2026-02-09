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


logger = logging.getLogger(__name__)


def create_resilient_session():
    """Crea una sesion HTTP con reintentos automaticos para errores transitorios."""
    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS"],
        raise_on_status=False,
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# Sesion global reutilizable
_http_session = create_resilient_session()


def exponential_backoff(attempt, base_delay=0.2, max_delay=10.0, jitter=True):
    """Calcula el tiempo de espera con backoff exponencial."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random())
    return delay


def rate_limit_wait(response=None, default_wait=0.2):
    """Espera inteligente basada en headers de rate limiting."""
    if response is not None:
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                wait_time = int(retry_after)
                logger.info(f"Rate limited. Esperando {wait_time}s (Retry-After header)")
                time.sleep(wait_time)
                return
            except ValueError:
                pass

        if response.status_code == 429:
            wait_time = exponential_backoff(attempt=2)
            logger.warning(f"Rate limited (429). Esperando {wait_time:.2f}s")
            time.sleep(wait_time)
            return

    time.sleep(default_wait)


# --- TOKEN AUTO-REFRESH ---

def get_valid_token(location_id):
    """
    Recupera el token. Primero verifica sin bloqueo si necesita refresco.
    Solo bloquea la fila (select_for_update) si realmente hay que refrescar,
    minimizando el tiempo de bloqueo en BD.
    """
    try:
        # Lectura rapida sin bloqueo
        try:
            token_obj = GHLToken.objects.get(location_id=location_id)
        except GHLToken.DoesNotExist:
            logger.error(f"No se encontro token para location_id: {location_id}")
            return None

        expiration_time = token_obj.updated_at + timedelta(seconds=token_obj.expires_in - 600)

        # Si no ha caducado, devolver directamente (sin bloqueo de BD)
        if timezone.now() <= expiration_time:
            return token_obj.access_token

        # Si ha caducado, bloquear la fila y refrescar
        logger.info(f"Token de {location_id} caducado. Refrescando...")
        with transaction.atomic():
            # Re-leer con bloqueo para evitar race condition
            token_obj = GHLToken.objects.select_for_update().get(location_id=location_id)

            # Doble check: otro proceso pudo haberlo refrescado mientras esperabamos
            expiration_time = token_obj.updated_at + timedelta(seconds=token_obj.expires_in - 600)
            if timezone.now() <= expiration_time:
                return token_obj.access_token

            return refresh_ghl_token(token_obj)

    except Exception as e:
        logger.error(f"Error critico obteniendo token seguro: {str(e)}", exc_info=True)
        return None


def refresh_ghl_token(token_obj):
    """
    Solicita un nuevo access_token a GHL usando el refresh_token.
    Se ejecuta dentro del lock de get_valid_token.
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
        # Timeout corto para no mantener la BD bloqueada demasiado
        response = _http_session.post(url, data=payload, timeout=10)
        new_data = response.json()

        if response.status_code == 200:
            token_obj.access_token = new_data.get('access_token')
            token_obj.refresh_token = new_data.get('refresh_token')
            token_obj.expires_in = new_data.get('expires_in', 86400)
            token_obj.save()
            logger.info(f"Token refrescado correctamente para {token_obj.location_id}")
            return token_obj.access_token
        else:
            logger.error(f"Error refrescando token GHL: {new_data}")
            return None
    except Exception as e:
        logger.error(f"Excepcion al refrescar token: {str(e)}")
        return None


# --- FUNCIONES DE API GHL (Asociaciones) ---

def ghl_get_current_associations(access_token, location_id, property_id):
    """Obtiene las asociaciones actuales de una propiedad."""
    rate_limit_wait()

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
        rate_limit_wait(response, default_wait=0)

        if response.status_code == 200:
            data = response.json()
            relations_list = data.get('relations', [])

            for rel in relations_list:
                r1 = rel.get('firstRecordId')
                r2 = rel.get('secondRecordId')
                contact_id = r2 if r1 == property_id else r1

                if contact_id:
                    found_relations_map[contact_id] = rel

            return found_relations_map
        elif response.status_code == 404:
            return {}
        else:
            logger.error(f"Error GHL GET Associations: {response.status_code}")
            return {}
    except Exception as e:
        logger.error(f"Excepcion GET Associations: {str(e)}")
        return {}


def ghl_delete_association(access_token, location_id, relation_id):
    """Elimina una asociacion en GHL."""
    rate_limit_wait()

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
        logger.error(f"Excepcion DELETE Association: {str(e)}")
        return False


def ghl_associate_records(access_token, location_id, property_id, contact_id, association_id):
    """Crea una asociacion entre propiedad y contacto."""
    rate_limit_wait()

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
        logger.error(f"Error asociando registros {contact_id}-{property_id}: {str(e)}")
        return False


def get_association_type_id(access_token, location_id, object_key="propiedad"):
    """Busca el ID de asociacion entre Contacto y el Custom Object."""
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

            logger.info(f"Buscando asociacion para '{target_singular}' en {location_id}...")

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
                    logger.info(f"ID Encontrado: {found_id}")
                    return found_id

            logger.warning(f"No se encontro ninguna asociacion compatible con '{object_key}'")
            return None

        else:
            logger.error(f"Error API GHL al buscar ID ({response.status_code}): {response.text}")
            return None

    except Exception as e:
        logger.error(f"Excepcion buscando Association ID: {str(e)}")
        return None


def ghlActualizarZonaAPI(locationId, opciones, token, url, prop):
    """Actualiza las opciones de zona en un campo personalizado de GHL."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        payload = {"options": opciones}
        if prop:
            payload["locationId"] = locationId
            payload["showInForms"] = True

        response = _http_session.put(url, headers=headers, json=payload, timeout=10)

        if response.status_code in [200, 204]:
            logger.info("Actualizacion exitosa de zonas en GHL")
            return response.json() if response.text else True
        else:
            logger.error(f"Error actualizando zonas {response.status_code}: {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error de conexion actualizando zonas: {str(e)}")
        return None
