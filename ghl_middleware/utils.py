# ghl_middleware/utils.py
import requests
import logging
import time
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import GHLToken

# Configuración del logger estándar de Django
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
    # Le restamos 600 segundos (10 min) de margen de seguridad
    expiration_time = token_obj.updated_at + timedelta(seconds=token_obj.expires_in - 600)
    
    if timezone.now() > expiration_time:
        logger.info(f"🔄 El token de {location_id} ha caducado. Refrescando...")
        return refresh_ghl_token(token_obj)
    
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
        'user_type': 'Location'
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        new_data = response.json()
        
        if response.status_code == 200:
            token_obj.access_token = new_data.get('access_token')
            token_obj.refresh_token = new_data.get('refresh_token')
            token_obj.expires_in = new_data.get('expires_in', 86400)
            token_obj.save()
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
    # CORRECCIÓN MÍNIMA Y ROBUSTA: 'Exception' en lugar de bare except
    except Exception as e:
        logger.error(f"❌ Error asociando registros {contact_id}-{property_id}: {str(e)}")
        return False

# --- NUEVA FUNCIÓN MEJORADA: AUTO-DETECCIÓN INTELIGENTE ---
def get_association_type_id(access_token, location_id, object_key="propiedad"):
    """
    Busca el ID de asociación entre Contacto y el Custom Object.
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
            
            target_singular = object_key.lower()          
            target_plural = target_singular + "es"        
            
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
    headers = {
        "Authorization": f"Bearer {token}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    # CAMBIO: print -> logger.debug
    logger.debug(f'Update Options Payload: {opciones}')
    
    try:
        payload = {"options": opciones}
        if prop:
            payload["locationId"] = locationId
            payload["showInForms"] = True
            
        response = requests.put(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code in [200, 204]:
            logger.info("✅ Actualización exitosa de zonas en GHL")
            return response.json() if response.text else True
        else:
            logger.error(f"❌ Error actualizando zonas {response.status_code}: {response.text}")
            return None

    except Exception as e:
        logger.error(f"💥 Error de conexión actualizando zonas: {str(e)}")
        return None