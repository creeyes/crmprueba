from django.urls import path
# IMPORTANTE: Aquí importamos AMBAS vistas
from .views import PublicPropertyList, PublicPropertyDetail

app_name = 'ghl_front'

urlpatterns = [
    # Ruta para el listado
    path('api/properties/', PublicPropertyList.as_view(), name='public_properties'),
    
    # Ruta para el detalle (Esta es la que daba error por no estar importada)
    path('api/properties/<str:ghl_contact_id>/', PublicPropertyDetail.as_view(), name='public_property_detail'),
]
