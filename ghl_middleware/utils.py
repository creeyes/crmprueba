import requests
import logging
import time
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import GHLToken

logger = logging.getLogger(__name__)

# --- NUEVAS FUNCIONES PARA TOKEN AUTO-REFRESH ---

def get_valid_token(location_id):
    """
    Recupera el token. Si ha caducado (o está a punto), lo refresca automáticamente.
    """
    try:
        token_obj = GHLToken.objects.get(location_id=location_id)
    except GHLToken.DoesNotExist:
        logger.error(f"❌ No se encontró token para location_id: {location_id}")
        return None

    # Calculamos cuándo caduca (updated_at + expires_in)
    # Le restamos 600 segundos (10 min) de margen de seguridad para no apurar
    expiration_time = token_obj.updated_at + timedelta(seconds=token_obj.expires_in - 600)
    
    if timezone.now() > expiration_time:
        logger.info(f"🔄 El token de {location_id} ha caducado. Refrescando...")
        return refresh_ghl_token(token_obj)
    
    # Si es válido, devolvemos el access_token actual
    return token_obj.access_token

def refresh_ghl_token(token_obj):
    """
    Solicita un nuevo access_token a GHL usando el refresh_token guardado.
    """
    url = "https://services.leadconnectorhq.com/oauth/token"
    payload = {
        'client_id': settings.GHL_CLIENT_ID,
        'client_secret': settings.GHL_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': token_obj.refresh_token,
        'user_type': 'Location' # Normalmente es Location para subcuentas
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        new_data = response.json()
        
        if response.status_code == 200:
            # Guardamos los nuevos datos en la BBDD
            token_obj.access_token = new_data.get('access_token')
            token_obj.refresh_token = new_data.get('refresh_token')
            token_obj.expires_in = new_data.get('expires_in', 86400)
            token_obj.save() # Esto actualiza 'updated_at' automáticamente
            logger.info(f"✅ Token refrescado correctamente para {token_obj.location_id}")
            return token_obj.access_token
        else:
            logger.error(f"❌ Error refrescando token GHL: {new_data}")
            return None
    except Exception as e:
        logger.error(f"❌ Excepción al refrescar token: {str(e)}")
        return None


# --- FUNCIONES EXISTENTES (Asociaciones) ---

def ghl_get_current_associations(access_token, location_id, property_id):
    time.sleep(0.5)
    headers = { "Authorization": f"Bearer {access_token}", "Version": "2021-07-28", "Accept": "application/json" }
    
    url = f"https://services.leadconnectorhq.com/associations/relations/{property_id}"
    params = { "locationId": location_id }
    found_relations_map = {}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
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
    time.sleep(0.2)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    url = f"https://services.leadconnectorhq.com/associations/relations/{relation_id}"
    params = { "locationId": location_id }

    try:
        response = requests.delete(url, headers=headers, params=params, timeout=10)
        return response.status_code in [200, 204]
    except Exception as e:
        logger.error(f"❌ Excepción DELETE Association: {str(e)}")
        return False

def ghl_associate_records(access_token, location_id, property_id, contact_id, association_id):
    time.sleep(0.2)
    headers = { "Authorization": f"Bearer {access_token}", "Version": "2021-07-28", "Content-Type": "application/json", "Accept": "application/json" }
    url = "https://services.leadconnectorhq.com/associations/relations"
    
    payload = {
        "locationId": location_id,
        "associationId": association_id, 
        "firstRecordId": contact_id,  
        "secondRecordId": property_id 
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.status_code in [200, 201]
    except:
        return False

# --- NUEVA FUNCIÓN MEJORADA: AUTO-DETECCIÓN INTELIGENTE ---
def get_association_type_id(access_token, location_id, object_key="propiedad"):
    """
    Busca el ID de asociación entre Contacto y el Custom Object.
    MEJORA: Ahora busca 'propiedad', 'propiedades' y 'custom_objects.propiedades'.
    """
    url = "https://services.leadconnectorhq.com/associations/types"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params={"locationId": location_id}, timeout=10)
        
        if response.status_code == 200:
            types = response.json().get('associationTypes', [])
            
            # Preparamos los términos de búsqueda (singular, plural, con s)
            target_singular = object_key.lower()          # propiedad
            target_plural = target_singular + "es"        # propiedades
            
            logger.info(f"🕵️ Buscando asociación para '{target_singular}' (o plurales) en {location_id}...")

            for t in types:
                # Obtenemos las keys de ambos lados. GHL usa firstObjectKey/secondObjectKey
                # pero a veces también sourceKey/targetKey. Revisamos todo por seguridad.
                keys_found = [
                    t.get('firstObjectKey', ''),
                    t.get('secondObjectKey', ''),
                    t.get('sourceKey', ''),
                    t.get('targetKey', '')
                ]
                # Limpiamos vacíos y pasamos a minúsculas
                keys_found = [k.lower() for k in keys_found if k]
                
                # 1. ¿Hay un contacto involucrado?
                is_contact = 'contact' in keys_found
                
                # 2. ¿Hay una propiedad involucrada? (Buscamos coincidencia parcial)
                # Esto detectará 'propiedad', 'propiedades' y 'custom_objects.propiedades'
                is_target = any((target_singular in k) for k in keys_found)
                
                if is_contact and is_target:
                    found_id = t['id']
                    logger.info(f"✅ ¡EUREKA! ID Encontrado: {found_id}")
                    return found_id
            
            logger.warning(f"⚠️ No se encontró ninguna asociación compatible con '{object_key}'")
            return None
            
        else:
            # Aquí capturamos el error 400 típico de cuentas nuevas sin uniones previas
            logger.error(f"❌ Error API GHL al buscar ID ({response.status_code}): {response.text}")
            return None

    except Exception as e:
        logger.error(f"❌ Excepción buscando Association ID: {str(e)}")
        return None

def ghlActualizarZonaAPI(locationId, opciones, token, url, prop):
    headers = {
        "Authorization": f"Bearer {token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    print(f'"options":{opciones}')
    try:
        # Enviamos la petición
        if prop:
            response = requests.put(
                url, 
                headers=headers, 
                json={
                    "locationId":locationId,
                    "showInForms": True,
                    "options":opciones
                    },  
                timeout=10
            )
        else:
            response = requests.put(
                url, 
                headers=headers, 
                json={"options":opciones}, 
                timeout=10
            )
        
        # Verificamos si GHL aceptó el cambio (200 OK o 204 No Content)
        if response.status_code in [200, 204]:
            print("✅ Actualización exitosa")
            return response.json() if response.text else True
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return None

    except Exception as e:
        print(f"💥 Error de conexión: {e}")
        return None