import logging
import requests
import json
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.db import transaction  # <--- INDISPENSABLE: Para integridad de datos
from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt
from .models import Agencia, Propiedad, Cliente, GHLToken, Provincia, Municipio, Zona
from .tasks import sync_associations_background, funcionAsyncronaZonas
from .utils import get_valid_token, get_association_type_id
# CORRECCIÓN #28: Helpers movidos a helpers.py para mejor organización
from .helpers import (
    clean_currency, clean_int, preferenciasTraductor1, 
    preferenciasTraductor2, estadoPropTrad, guardadorURL
)
# CORRECCIÓN #27: Lógica de matching extraída a matching.py
from .matching import (
    buscar_clientes_para_propiedad, buscar_propiedades_para_cliente,
    actualizar_relaciones_propiedad, actualizar_relaciones_cliente
)

logger = logging.getLogger(__name__)

# --- HELPER INTERNO: PORTADA / HEALTH CHECK ---
# CORRECCIÓN #34: Convertido en health check real que verifica conexión a BD
class HomeView(APIView):
    permission_classes = []
    
    def get(self, request):
        from django.db import connection
        
        health_status = {
            "status": "healthy",
            "message": "Server is running 🚀",
            "checks": {}
        }
        
        # Verificar conexión a base de datos
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status["checks"]["database"] = "connected"
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["checks"]["database"] = "disconnected"
            logger.error(f"❌ Health check DB failed: {str(e)}")
        
        status_code = 200 if health_status["status"] == "healthy" else 503
        return Response(health_status, status=status_code)

# -------------------------------------------------------------------------
# VISTA 1: OAUTH CALLBACK (MODIFICADA: SEGURIDAD Y ATOMICIDAD)
# -------------------------------------------------------------------------
class GHLOAuthCallbackView(APIView):
    permission_classes = []
    
    def get(self, request):
        code = request.query_params.get('code')
        if not code: return Response({"error": "No code provided"}, status=400)
        
        token_url = "https://services.leadconnectorhq.com/oauth/token"
        data = {
            'client_id': settings.GHL_CLIENT_ID,
            'client_secret': settings.GHL_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.GHL_REDIRECT_URI,
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=15) # Timeout añadido por seguridad
            tokens = response.json()
            
            if response.status_code == 200:
                # INICIO TRANSACCIÓN: O todo se guarda o nada se guarda
                with transaction.atomic():
                    location_id = tokens.get('locationId')
                    access_token = tokens['access_token']

                    # 1. Guardar/Actualizar Token
                    GHLToken.objects.update_or_create(
                        location_id=location_id,
                        defaults={
                            'access_token': access_token,
                            'refresh_token': tokens['refresh_token'],
                            'token_type': tokens['token_type'],
                            'expires_in': tokens['expires_in'],
                            'scope': tokens['scope']
                        }
                    )
                    
                    # 2. Crear Agencia si no existe
                    agencia, created = Agencia.objects.get_or_create(location_id=location_id, defaults={'active': True})
                    
                    # 3. Auto-detección ID
                    logger.info(f"🕵️ Buscando ID de asociación para {location_id}...")
                    found_id = get_association_type_id(access_token, location_id, object_key="propiedad")
                    
                    if found_id:
                        agencia.association_type_id = found_id
                        agencia.save()
                        logger.info(f"✅ ID de asociación detectado y guardado: {found_id}")
                    else:
                        logger.warning(f"⚠️ No se pudo detectar el ID automáticamente.")

                return Response({"message": "App instalada y configurada.", "location_id": location_id}, status=200)
            
            logger.error(f"❌ Error OAuth GHL Respuesta: {tokens}")
            return Response({"error": "Fallo en la autenticación con GHL."}, status=400)

        except Exception as e:
            # CORRECCIÓN SEGURIDAD: Loguear traza completa, ocultar detalle al cliente
            logger.error(f"❌ Excepción crítica en OAuth: {str(e)}", exc_info=True)
            return Response(
                {"error": "Ha ocurrido un error interno durante la instalación."}, 
                status=500
            )

# -------------------------------------------------------------------------
# VISTA 2: WEBHOOK PROPIEDAD
# -------------------------------------------------------------------------

class WebhookPropiedadView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            data = request.data
            logger.info(f"📥 Webhook Propiedad: {data}")

            custom_data = data.get('customData', {})
            location_data = data.get('location', {})
            location_id = location_data.get('id') or custom_data.get('location_id')

            if not location_id:
                return Response({'error': 'Missing location_id'}, status=400)

            agencia = get_object_or_404(Agencia, location_id=location_id)
            ghl_record_id = custom_data.get('contact_id') or data.get('id')

            if not ghl_record_id:
                 return Response({'error': 'Missing Record ID'}, status=400)

            # TRANSACCIÓN: Garantiza que update_or_create + zona + matches se aplican juntos
            with transaction.atomic():
                prop_data = {
                    'agencia': agencia,
                    'ghl_contact_id': ghl_record_id,
                    'precio': clean_currency(custom_data.get('precio') or data.get('precio')),
                    'habitaciones': clean_int(custom_data.get('habitaciones') or data.get('habitaciones')),
                    'estado': estadoPropTrad(custom_data.get("estado")),
                    'animales': preferenciasTraductor1(custom_data.get('animales')),
                    'metros': clean_int(custom_data.get('metros')),
                    'balcon': preferenciasTraductor1(custom_data.get('balcon')),
                    'garaje': preferenciasTraductor1(custom_data.get('garaje')),
                    'patioInterior': preferenciasTraductor1(custom_data.get('patioInterior')),
                    'imagenesUrl': guardadorURL(custom_data.get('imagenesUrl')),
                }

                propiedad, created = Propiedad.objects.update_or_create(
                    agencia=agencia,
                    ghl_contact_id=ghl_record_id,
                    defaults=prop_data
                )

                zona = custom_data.get("zona")
                if (zona):
                    zonaLimpio = zona.replace("_"," ").lower().strip()
                    zonaObj = Zona.objects.filter(nombre__iexact=zonaLimpio).first()
                    if (zonaObj):
                        propiedad.zona = zonaObj
                        propiedad.save()

                if (propiedad.estado == Propiedad.estadoPiso.ACTIVO):
                    # CORRECCIÓN #27: Usar funciones centralizadas de matching.py
                    clientes_match = buscar_clientes_para_propiedad(propiedad, agencia)
                    matches_count = actualizar_relaciones_propiedad(propiedad, clientes_match)
                else:
                    clientes_match = Cliente.objects.none()
                    matches_count = 0

            # 3. SINCRONIZACIÓN CON GHL (fuera de la transacción: llamadas HTTP externas)
            if matches_count > 0:
                if not agencia.association_type_id:
                    logger.warning(f"⚠️ Agencia {location_id} no tiene 'association_type_id'. Cruzado saltado.")
                    return Response({'status': 'warning', 'msg': 'Falta Association ID', 'matches_found': matches_count})

                access_token = get_valid_token(location_id)

                if access_token:
                    target_ids = [c.ghl_contact_id for c in clientes_match]

                    sync_associations_background(
                        access_token=access_token,
                        location_id=location_id,
                        origin_record_id=propiedad.ghl_contact_id,
                        target_ids_list=target_ids,
                        association_id_val=agencia.association_type_id
                    )
                else:
                    logger.warning(f"⚠️ No token valid found for {location_id}")

            return Response({'status': 'success', 'matches_found': matches_count})

        except Exception as e:
            logger.error(f"❌ Error en Webhook Propiedad: {str(e)}", exc_info=True)
            return Response({"error": "Error interno procesando propiedad"}, status=500)

# -------------------------------------------------------------------------
# VISTA 3: WEBHOOK CLIENTE
# -------------------------------------------------------------------------

class WebhookClienteView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            data = request.data
            logger.info(f"📥 Webhook Cliente: {data}")
            
            custom_data = data.get('customData', {}) 
            location_data = data.get('location', {})
            location_id = location_data.get('id') or custom_data.get('location_id')
        
            if not location_id: return Response({'error': 'Missing location_id'}, status=400)
                
            agencia = get_object_or_404(Agencia, location_id=location_id)
            ghl_contact_id = data.get('id') or custom_data.get('contact_id')
            if not ghl_contact_id: return Response({'error': 'Missing Contact ID'}, status=400)

            # TRANSACCIÓN: Garantiza que update_or_create + zonas + matches se aplican juntos
            with transaction.atomic():
                cliente_data = {
                    'agencia': agencia,
                    'ghl_contact_id': ghl_contact_id,
                    'nombre': custom_data.get('full_name'),
                    'presupuesto_maximo': clean_currency(custom_data.get('presupuesto') or data.get('presupuesto')),
                    'habitaciones_minimas': clean_int(custom_data.get('habitaciones') or data.get('habitaciones_min')),
                    'animales': preferenciasTraductor1(custom_data.get('animales')),
                    'metrosMinimo': clean_int(custom_data.get('metros')),
                    'balcon': preferenciasTraductor2(custom_data.get('balcon')),
                    'garaje': preferenciasTraductor2(custom_data.get('garaje')),
                    'patioInterior': preferenciasTraductor2(custom_data.get('patioInterior')),
                }

                cliente, created = Cliente.objects.update_or_create(
                    agencia=agencia,
                    ghl_contact_id=ghl_contact_id,
                    defaults=cliente_data
                )

                zona_nombre = custom_data.get("zona_interes")
                if zona_nombre:
                    zona_lista = [z.strip() for z in str(zona_nombre).split(",")]
                    logger.debug(f"📍 Procesando zonas de interés para {ghl_contact_id}: {zona_lista}")

                    zonas = Zona.objects.filter(nombre__in=zona_lista)
                    cliente.zona_interes.set(zonas)
                    cliente.save()

                # CORRECCIÓN #27: Usar funciones centralizadas de matching.py
                propiedades_match = buscar_propiedades_para_cliente(cliente, agencia)
                matches_count = actualizar_relaciones_cliente(cliente, propiedades_match)
                logger.info(f"✅ Matches encontrados para {cliente.ghl_contact_id}: {matches_count}")

            # SINCRONIZACIÓN CON GHL (fuera de la transacción: llamadas HTTP externas)
            if matches_count > 0:
                if not agencia.association_type_id:
                    logger.warning(f"⚠️ Agencia {location_id} no tiene 'association_type_id'. Cruzado saltado.")
                    return Response({'status': 'warning', 'msg': 'Falta Association ID', 'matches_found': matches_count})

                access_token = get_valid_token(location_id)

                if access_token:
                    for prop in propiedades_match:
                        todos_los_interesados = prop.interesados.all()
                        target_ids = [c.ghl_contact_id for c in todos_los_interesados]

                        sync_associations_background(
                            access_token=access_token,
                            location_id=location_id,
                            origin_record_id=prop.ghl_contact_id,
                            target_ids_list=target_ids,
                            association_id_val=agencia.association_type_id
                        )
                else:
                    logger.warning(f"⚠️ No token valid found for {location_id}")

            return Response({'status': 'success', 'matches_found': matches_count})

        except Exception as e:
            logger.error(f"❌ Error en Webhook Cliente: {str(e)}", exc_info=True)
            return Response({"error": "Error interno procesando cliente"}, status=500)

# -------------------------------------------------------------------------
# ENDPOINTS AUXILIARES (CORREGIDO: REGISTRAR UBICACIÓN)
# -------------------------------------------------------------------------

def api_get_zonas_tree(request):
    try:
        provincias = Provincia.objects.prefetch_related('municipios__zonas').all()
        arbol = []
        for p in provincias:
            municipios_p = []
            for m in p.municipios.all():
                municipios_p.append({
                    "nombre": m.nombre,
                    "zonas": list(m.zonas.values_list('nombre', flat=True))
                })
            arbol.append({
                "provincia": p.nombre,
                "municipios": municipios_p
            })
        return JsonResponse({"zonas": arbol})
    except Exception as e:
        logger.error(f"Error obteniendo zonas: {str(e)}", exc_info=True)
        return JsonResponse({"error": "Error interno"}, status=500)

@csrf_exempt
def registrar_ubicacion(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    try:
        datos = json.loads(request.body)
        nombre_prov = datos.get('provincia', '').strip()
        nombre_muni = datos.get('municipio', '').strip()
        nombre_zona = datos.get('zona', '').strip()

        if not nombre_prov or not nombre_muni or not nombre_zona:
            return JsonResponse({
                'status': 'error', 
                'message': 'Faltan datos obligatorios. Debes indicar Zona, Municipio y Provincia.'
            }, status=400)

        # ATOMICIDAD: Prevenir datos corruptos si falla a mitad
        with transaction.atomic():
            # Creamos/Buscamos Provincia
            prov_obj, prov_creada = Provincia.objects.get_or_create(
                nombre__iexact=nombre_prov, 
                defaults={'nombre': nombre_prov}
            )

            # Creamos/Buscamos Municipio
            muni_obj, muni_creado = Municipio.objects.get_or_create(
                nombre__iexact=nombre_muni,
                provincia=prov_obj,
                defaults={'nombre': nombre_muni}
            )

            # Creamos/Buscamos Zona
            zona_obj, zona_creada = Zona.objects.get_or_create(
                nombre__iexact=nombre_zona,
                municipio=muni_obj,
                defaults={'nombre': nombre_zona}
            )

        # Lógica asíncrona fuera del bloque transaccional crítico
        if zona_creada:
            funcionAsyncronaZonas()

        si_algo_es_nuevo = prov_creada or muni_creado or zona_creada

        return JsonResponse({
            'status': 'success',
            'message': 'Se ha creado el registro correctamente' if si_algo_es_nuevo else 'No se ha hecho nada (ya existía todo)'
        })

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)

    except Exception as e:
        # CORRECCIÓN SEGURIDAD: No exponer detalle del error
        logger.error(f"❌ Error registrando ubicación: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': 'Error interno del servidor.'
        }, status=500)