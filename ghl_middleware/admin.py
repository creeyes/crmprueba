from django.contrib import admin
from .models import Agencia, Propiedad, Cliente, GHLToken, Zona, Municipio, Provincia

# Esto hace que aparezcan en el panel y se vean bonitos con columnas

admin.site.register(Agencia)
admin.site.register(Propiedad)
admin.site.register(Cliente)
admin.site.register(GHLToken)
admin.site.register(Zona)
admin.site.register(Municipio)
admin.site.register(Provincia)
# @admin.register(Agencia)
# class AgenciaAdmin(admin.ModelAdmin):
#     # Agregué 'active' que pusimos en el modelo
#     list_display = ('nombre', 'location_id', 'active', 'api_key')
#     search_fields = ('nombre', 'location_id')
#     list_filter = ('active',)

# @admin.register(Propiedad)
# class PropiedadAdmin(admin.ModelAdmin):
#     list_display = ('zona', 'precio', 'habitaciones', 'estado', 'agencia')
#     list_filter = ('estado', 'zona', 'agencia')
#     search_fields = ('zona', 'ghl_contact_id')

# @admin.register(Cliente)
# class ClienteAdmin(admin.ModelAdmin):
#     list_display = ('nombre', 'presupuesto_maximo', 'zona_interes', 'agencia')
#     list_filter = ('zona_interes', 'agencia')
#     search_fields = ('nombre',)

# # IMPORTANTE: Para ver si el "Cruzado" está funcionando y guardando tokens
# @admin.register(GHLToken)
# class GHLTokenAdmin(admin.ModelAdmin):
#     list_display = ('location_id', 'token_type', 'expires_in', 'updated_at')
#     search_fields = ('location_id',)
