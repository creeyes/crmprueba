from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
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
