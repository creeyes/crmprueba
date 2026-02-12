from django.urls import path
# Importamos también la vista del OAuth (GHLOAuthCallbackView) y la nueva GHLLaunchView
from .views import WebhookPropiedadView, WebhookClienteView, GHLOAuthCallbackView
from . import views

urlpatterns = [
    

    # --- 2. RUTA OBLIGATORIA PARA INSTALAR LA APP (El Cruzado) ---
    # GHL llamará aquí: https://tu-dominio.railway.app/api/oauth/callback/
    path('oauth/callback/', GHLOAuthCallbackView.as_view(), name='ghl_oauth_callback'),

    # --- 3. TUS WEBHOOKS DE NEGOCIO ---
    path('webhooks/propiedad/', WebhookPropiedadView.as_view(), name='webhook_propiedad'),
    path('webhooks/cliente/', WebhookClienteView.as_view(), name='webhook_cliente'),
    
    # CORRECCIÓN #33: Endpoints de zonas movidos a /api/zonas/ (no son webhooks)
    path('zonas/', views.api_get_zonas_tree, name='get_zonas_tree'),
    path('zonas/nuevo/', views.registrar_ubicacion, name='add_zonas_tree'),
]










