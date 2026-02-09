from django.contrib import admin
from .models import Agencia, Propiedad, Cliente, GHLToken, Zona, Municipio, Provincia


@admin.register(Agencia)
class AgenciaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'location_id', 'active')
    search_fields = ('nombre', 'location_id')
    list_filter = ('active',)


@admin.register(Propiedad)
class PropiedadAdmin(admin.ModelAdmin):
    list_display = ('ghl_contact_id', 'zona', 'precio', 'habitaciones', 'estado', 'agencia')
    list_filter = ('estado', 'agencia')
    search_fields = ('ghl_contact_id',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'ghl_contact_id', 'presupuesto_maximo', 'agencia')
    list_filter = ('agencia',)
    search_fields = ('nombre', 'ghl_contact_id')


@admin.register(GHLToken)
class GHLTokenAdmin(admin.ModelAdmin):
    list_display = ('location_id', 'token_type', 'expires_in', 'updated_at')
    search_fields = ('location_id',)


@admin.register(Provincia)
class ProvinciaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'provincia')
    list_filter = ('provincia',)
    search_fields = ('nombre',)


@admin.register(Zona)
class ZonaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'municipio')
    list_filter = ('municipio__provincia',)
    search_fields = ('nombre',)
