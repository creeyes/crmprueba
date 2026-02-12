from django.urls import path
# Importar todas las vistas (incluyendo las nuevas)
from .views import (
    PublicPropertyList,
    PublicPropertyDetail,
    PublicPropertyFilteredList,
    PublicLocationsList
)

app_name = 'ghl_front'

urlpatterns = [
    # Listado básico (mantener para compatibilidad)
    path('api/properties/', PublicPropertyList.as_view(), name='public_properties'),

    # NUEVO: Listado con filtros avanzados
    path('api/properties/search/', PublicPropertyFilteredList.as_view(), name='properties_search'),

    # Detalle de propiedad (el orden importa: debe ir DESPUÉS de search/)
    path('api/properties/<str:ghl_contact_id>/', PublicPropertyDetail.as_view(), name='public_property_detail'),

    # NUEVO: Ubicaciones disponibles
    path('api/locations/', PublicLocationsList.as_view(), name='public_locations'),
]
