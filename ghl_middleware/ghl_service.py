# ghl_middleware/ghl_service.py
import logging
from .utils import _http_session, get_valid_token

logger = logging.getLogger(__name__)


def create_contact_in_ghl(agencia, contact_data: dict) -> str | None:
    """
    Crea un contacto en GHL y devuelve su ghl_contact_id.
    """
    token = get_valid_token(agencia.location_id)
    if not token:
        logger.error(f"No se pudo obtener token para {agencia.location_id}")
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Version": "2021-07-28"
    }

    payload = {
        "locationId": agencia.location_id,
        "firstName":  contact_data.get("first_name", ""),
        "lastName":   contact_data.get("last_name", ""),
        "email":      contact_data.get("email", ""),
        "phone":      contact_data.get("phone", ""),
    }

    try:
        response = _http_session.post(
            "https://services.leadconnectorhq.com/contacts/",
            json=payload,
            headers=headers,
            timeout=10
        )

        if response.ok:
            contact_id = response.json().get("contact", {}).get("id")
            logger.info(f"Contacto creado en GHL: {contact_id}")
            return contact_id

        logger.error(f"Error creando contacto en GHL: {response.status_code} - {response.text}")
        return None

    except Exception as e:
        logger.error(f"Excepción creando contacto en GHL: {str(e)}")
        return None

