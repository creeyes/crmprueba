# ghl_middleware/tests.py
"""
CORRECCIÓN #41: Tests unitarios para el proyecto CRM.
Cubre: matching, helpers, API pública.
"""
from decimal import Decimal
from django.test import TestCase, Client as HttpClient
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from .models import Agencia, Propiedad, Cliente, Zona, Municipio, Provincia
from .helpers import (
    clean_currency, clean_int, preferenciasTraductor1,
    preferenciasTraductor2, estadoPropTrad, guardadorURL
)
from .matching import (
    buscar_clientes_para_propiedad, buscar_propiedades_para_cliente,
    actualizar_relaciones_propiedad, actualizar_relaciones_cliente
)


# =============================================================================
# TESTS PARA HELPERS
# =============================================================================

class CleanCurrencyTests(TestCase):
    """Tests para la función clean_currency"""
    
    def test_valor_normal(self):
        self.assertEqual(clean_currency("1234.56"), 1234.56)
    
    def test_valor_con_simbolo_dolar(self):
        self.assertEqual(clean_currency("$1,234.56"), 1234.56)
    
    def test_valor_con_comas(self):
        self.assertEqual(clean_currency("1,234,567"), 1234567.0)
    
    def test_valor_none(self):
        self.assertEqual(clean_currency(None), 0.0)
    
    def test_valor_vacio(self):
        self.assertEqual(clean_currency(""), 0.0)
    
    def test_valor_invalido(self):
        self.assertEqual(clean_currency("abc"), 0.0)
    
    def test_valor_con_espacios(self):
        self.assertEqual(clean_currency("  1234  "), 1234.0)


class CleanIntTests(TestCase):
    """Tests para la función clean_int"""
    
    def test_valor_normal(self):
        self.assertEqual(clean_int("5"), 5)
    
    def test_valor_decimal(self):
        self.assertEqual(clean_int("3.7"), 3)
    
    def test_valor_none(self):
        self.assertEqual(clean_int(None), 0)
    
    def test_valor_vacio(self):
        self.assertEqual(clean_int(""), 0)
    
    def test_valor_invalido(self):
        self.assertEqual(clean_int("abc"), 0)


class PreferenciasTraductorTests(TestCase):
    """Tests para las funciones de traducción de preferencias"""
    
    def test_preferencias1_si(self):
        result = preferenciasTraductor1("si")
        self.assertEqual(result, Cliente.Preferencias1.SI)
    
    def test_preferencias1_no(self):
        result = preferenciasTraductor1("no")
        self.assertEqual(result, Cliente.Preferencias1.NO)
    
    def test_preferencias1_mayusculas(self):
        result = preferenciasTraductor1("SI")
        self.assertEqual(result, Cliente.Preferencias1.SI)
    
    def test_preferencias1_none(self):
        result = preferenciasTraductor1(None)
        self.assertEqual(result, Cliente.Preferencias1.NO)
    
    def test_preferencias2_si(self):
        result = preferenciasTraductor2("si")
        self.assertEqual(result, Cliente.Preferencias2.SI)
    
    def test_preferencias2_indiferente(self):
        result = preferenciasTraductor2("indiferente")
        self.assertEqual(result, Cliente.Preferencias2.IND)
    
    def test_preferencias2_none(self):
        result = preferenciasTraductor2(None)
        self.assertEqual(result, Cliente.Preferencias2.IND)


class EstadoPropTradTests(TestCase):
    """Tests para la traducción de estados de propiedad"""
    
    def test_vendido(self):
        result = estadoPropTrad("vendido")
        self.assertEqual(result, Propiedad.estadoPiso.VENDIDO)
    
    def test_a_la_venta(self):
        result = estadoPropTrad("a la venta")
        self.assertEqual(result, Propiedad.estadoPiso.ACTIVO)
    
    def test_con_guiones_bajos(self):
        result = estadoPropTrad("a_la_venta")
        self.assertEqual(result, Propiedad.estadoPiso.ACTIVO)
    
    def test_no_oficial(self):
        result = estadoPropTrad("no es oficial")
        self.assertEqual(result, Propiedad.estadoPiso.NoOficial)
    
    def test_valor_desconocido(self):
        result = estadoPropTrad("pendiente")
        self.assertEqual(result, Propiedad.estadoPiso.NoOficial)


class GuardadorURLTests(TestCase):
    """Tests para la extracción de URLs de imágenes"""
    
    def test_lista_valida(self):
        data = [{"url": "http://img1.jpg"}, {"url": "http://img2.jpg"}]
        result = guardadorURL(data)
        self.assertEqual(result, ["http://img1.jpg", "http://img2.jpg"])
    
    def test_lista_con_items_sin_url(self):
        data = [{"url": "http://img1.jpg"}, {"name": "img2"}]
        result = guardadorURL(data)
        self.assertEqual(result, ["http://img1.jpg"])
    
    def test_valor_none(self):
        result = guardadorURL(None)
        self.assertEqual(result, [])
    
    def test_valor_null_string(self):
        result = guardadorURL("null")
        self.assertEqual(result, [])
    
    def test_valor_no_lista(self):
        result = guardadorURL("string")
        self.assertEqual(result, [])


# =============================================================================
# TESTS PARA MATCHING
# =============================================================================

class MatchingTestCase(TestCase):
    """Tests para la lógica de matching entre propiedades y clientes"""
    
    @classmethod
    def setUpTestData(cls):
        """Crear datos de prueba compartidos"""
        # Crear agencia
        cls.agencia = Agencia.objects.create(
            location_id="test-agency-123",
            nombre="Agencia Test",
            active=True
        )
        
        # Crear ubicación
        cls.provincia = Provincia.objects.create(nombre="Barcelona")
        cls.municipio = Municipio.objects.create(
            nombre="Cornellà",
            provincia=cls.provincia
        )
        cls.zona = Zona.objects.create(
            nombre="Almeda",
            municipio=cls.municipio
        )
        
        # Crear propiedad activa
        cls.propiedad = Propiedad.objects.create(
            agencia=cls.agencia,
            ghl_contact_id="prop-001",
            precio=Decimal("250000.00"),
            habitaciones=3,
            metros=100,
            estado=Propiedad.estadoPiso.ACTIVO,
            zona=cls.zona,
            animales=Propiedad.Preferencias1.SI,
            balcon=Propiedad.Preferencias1.SI,
            garaje=Propiedad.Preferencias1.NO,
            patioInterior=Propiedad.Preferencias1.NO
        )
        
        # Crear cliente que hace match
        cls.cliente_match = Cliente.objects.create(
            agencia=cls.agencia,
            ghl_contact_id="cli-001",
            nombre="Cliente Match",
            presupuesto_maximo=Decimal("300000.00"),
            habitaciones_minimas=2,
            metrosMinimo=80,
            animales=Cliente.Preferencias1.SI,
            balcon=Cliente.Preferencias2.SI,
            garaje=Cliente.Preferencias2.IND,
            patioInterior=Cliente.Preferencias2.IND
        )
        cls.cliente_match.zona_interes.add(cls.zona)
        
        # Crear cliente que NO hace match (presupuesto bajo)
        cls.cliente_no_match = Cliente.objects.create(
            agencia=cls.agencia,
            ghl_contact_id="cli-002",
            nombre="Cliente No Match",
            presupuesto_maximo=Decimal("100000.00"),  # Muy bajo
            habitaciones_minimas=2,
            metrosMinimo=80,
            animales=Cliente.Preferencias1.NO,
            balcon=Cliente.Preferencias2.IND,
            garaje=Cliente.Preferencias2.IND,
            patioInterior=Cliente.Preferencias2.IND
        )
        cls.cliente_no_match.zona_interes.add(cls.zona)
    
    def test_buscar_clientes_para_propiedad_encuentra_match(self):
        """Debe encontrar clientes que hacen match"""
        clientes = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        self.assertIn(self.cliente_match, clientes)
    
    def test_buscar_clientes_para_propiedad_excluye_no_match(self):
        """Debe excluir clientes que no hacen match por presupuesto"""
        clientes = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        self.assertNotIn(self.cliente_no_match, clientes)
    
    def test_buscar_propiedades_para_cliente(self):
        """Debe encontrar propiedades para un cliente"""
        propiedades = buscar_propiedades_para_cliente(self.cliente_match, self.agencia)
        self.assertIn(self.propiedad, propiedades)
    
    def test_actualizar_relaciones_propiedad(self):
        """Debe actualizar correctamente las relaciones M2M"""
        clientes = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        count = actualizar_relaciones_propiedad(self.propiedad, clientes)
        self.assertGreater(count, 0)
        self.assertIn(self.propiedad, self.cliente_match.propiedades_interes.all())
    
    def test_actualizar_relaciones_cliente(self):
        """Debe actualizar correctamente las relaciones M2M"""
        propiedades = buscar_propiedades_para_cliente(self.cliente_match, self.agencia)
        count = actualizar_relaciones_cliente(self.cliente_match, propiedades)
        self.assertGreater(count, 0)


# =============================================================================
# TESTS PARA API PÚBLICA
# =============================================================================

class HealthCheckAPITests(APITestCase):
    """Tests para el endpoint de health check"""
    
    def test_health_check_returns_200(self):
        """El health check debe devolver 200 si la DB funciona"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)
    
    def test_health_check_contains_database_status(self):
        """El health check debe incluir el estado de la base de datos"""
        response = self.client.get('/')
        self.assertIn('checks', response.data)
        self.assertIn('database', response.data['checks'])


class ZonasAPITests(TestCase):
    """Tests para el endpoint de zonas"""
    
    @classmethod
    def setUpTestData(cls):
        cls.provincia = Provincia.objects.create(nombre="Madrid")
        cls.municipio = Municipio.objects.create(
            nombre="Madrid Centro",
            provincia=cls.provincia
        )
        cls.zona = Zona.objects.create(
            nombre="Chamberí",
            municipio=cls.municipio
        )
    
    def test_get_zonas_tree_returns_200(self):
        """El endpoint de zonas debe devolver 200"""
        client = HttpClient()
        response = client.get('/api/zonas/')
        self.assertEqual(response.status_code, 200)
    
    def test_get_zonas_tree_contains_data(self):
        """El endpoint debe devolver la estructura de zonas"""
        client = HttpClient()
        response = client.get('/api/zonas/')
        data = response.json()
        self.assertIn('zonas', data)
        self.assertEqual(len(data['zonas']), 1)
        self.assertEqual(data['zonas'][0]['provincia'], 'Madrid')
