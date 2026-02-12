from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from ghl_middleware.models import Propiedad
from .serializers import PropiedadPublicaSerializer


# CORRECCIÓN #23: Paginación para evitar devolver todos los datos de golpe
class PropiedadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PublicPropertyList(generics.ListAPIView):
    serializer_class = PropiedadPublicaSerializer
    authentication_classes = []  # API abierta
    permission_classes = []
    pagination_class = PropiedadPagination  # CORRECCIÓN #23

    def get_queryset(self):
        # VERSIÓN SIMPLE:
        # Esperamos que nos pasen el ID en la URL: ?agency_id=ABC-123
        agency_id = self.request.query_params.get('agency_id')

        if agency_id:
            # Filtramos propiedades de esa agencia que estén activas
            # CORRECCIÓN #22: select_related para evitar N+1 queries
            return Propiedad.objects.select_related('zona__municipio').filter(
                agencia__location_id=agency_id, 
                estado='activo'
            )
        
        # Si no pasan ID, devolvemos vacío para no mezclar datos
        return Propiedad.objects.none()


class PublicPropertyDetail(generics.RetrieveAPIView):
    """
    Vista para obtener el detalle de una sola propiedad usando su GHL Contact ID.
    """
    serializer_class = PropiedadPublicaSerializer
    lookup_field = 'ghl_contact_id'  # IMPORTANTE: Buscamos por el ID de GHL, no el ID numérico de Django
    authentication_classes = []
    permission_classes = []

    def get_queryset(self):
        # CORRECCIÓN #21: Filtrar por agency_id para que una agencia no vea propiedades de otra
        agency_id = self.request.query_params.get('agency_id')

        # CORRECCIÓN #22: select_related para evitar N+1 queries
        queryset = Propiedad.objects.select_related('zona__municipio').filter(estado='activo')

        if agency_id:
            queryset = queryset.filter(agencia__location_id=agency_id)

        return queryset


# ========== NUEVOS ENDPOINTS CON FILTROS AVANZADOS ==========

class PublicPropertyFilteredList(generics.ListAPIView):
    """
    Endpoint con filtros avanzados para búsqueda de propiedades.

    Query params disponibles:
    - agency_id (requerido): ID de la agencia
    - type: Villa | Apartment | Studio
    - location: Nombre de la zona
    - min_price: Precio mínimo
    - max_price: Precio máximo
    - beds: Número exacto de habitaciones
    - min_sqm: Metros cuadrados mínimos
    - features: Balcón,Garaje,Mascotas,Patio (separados por coma)
    - ordering: Campo de ordenamiento (default: -precio)
    """
    serializer_class = PropiedadPublicaSerializer
    authentication_classes = []
    permission_classes = []
    pagination_class = PropiedadPagination

    def get_queryset(self):
        agency_id = self.request.query_params.get('agency_id')

        if not agency_id:
            return Propiedad.objects.none()

        # Base queryset
        queryset = Propiedad.objects.select_related('zona__municipio').filter(
            agencia__location_id=agency_id,
            estado='activo'
        )

        # Filtro por tipo de propiedad
        tipo = self.request.query_params.get('type')
        if tipo == 'Villa':
            queryset = queryset.filter(habitaciones__gt=4)
        elif tipo == 'Studio':
            queryset = queryset.filter(habitaciones=0)
        elif tipo == 'Apartment':
            queryset = queryset.filter(habitaciones__gte=1, habitaciones__lte=4)

        # Filtro por ubicación (zona)
        location = self.request.query_params.get('location')
        if location:
            queryset = queryset.filter(zona__nombre__iexact=location)

        # Filtros por precio
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(precio__gte=min_price)
        if max_price:
            queryset = queryset.filter(precio__lte=max_price)

        # Filtro por número de habitaciones
        beds = self.request.query_params.get('beds')
        if beds:
            queryset = queryset.filter(habitaciones=beds)

        # Filtro por metros cuadrados mínimos
        min_sqm = self.request.query_params.get('min_sqm')
        if min_sqm:
            queryset = queryset.filter(metros__gte=min_sqm)

        # Filtros por características
        features = self.request.query_params.get('features')
        if features:
            feature_list = [f.strip().lower() for f in features.split(',')]

            if 'balcón' in feature_list or 'balcon' in feature_list:
                queryset = queryset.filter(balcon='si')

            if 'garaje' in feature_list:
                queryset = queryset.filter(garaje='si')

            if 'mascotas' in feature_list or 'animales' in feature_list:
                queryset = queryset.filter(animales='si')

            if 'patio' in feature_list:
                queryset = queryset.filter(patioInterior='si')

        # Ordenamiento
        ordering = self.request.query_params.get('ordering', '-precio')
        queryset = queryset.order_by(ordering)

        return queryset


class PublicLocationsList(APIView):
    """
    Devuelve todas las ubicaciones (zonas) disponibles para una agencia.
    Útil para popular dropdowns de filtros en el frontend.

    Query params:
    - agency_id (requerido): ID de la agencia
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        agency_id = request.query_params.get('agency_id')

        if not agency_id:
            return Response(
                {'error': 'agency_id es requerido'},
                status=http_status.HTTP_400_BAD_REQUEST
            )

        # Obtener zonas únicas de propiedades activas de la agencia
        zonas = Propiedad.objects.filter(
            agencia__location_id=agency_id,
            estado='activo',
            zona__isnull=False
        ).select_related('zona__municipio__provincia').values(
            'zona__nombre',
            'zona__municipio__nombre',
            'zona__municipio__provincia__nombre'
        ).distinct()

        # Formatear respuesta
        locations = [
            {
                'zona': z['zona__nombre'],
                'municipio': z['zona__municipio__nombre'],
                'provincia': z['zona__municipio__provincia__nombre']
            }
            for z in zonas
        ]

        return Response({
            'count': len(locations),
            'locations': locations
        })
