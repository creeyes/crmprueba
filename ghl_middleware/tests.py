"""
Tests unitarios para el proyecto CRM.
Cubre: matching, helpers, API publica.
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
    def test_preferencias1_si(self):
        self.assertEqual(preferenciasTraductor1("si"), Cliente.Preferencias1.SI)

    def test_preferencias1_no(self):
        self.assertEqual(preferenciasTraductor1("no"), Cliente.Preferencias1.NO)

    def test_preferencias1_mayusculas(self):
        self.assertEqual(preferenciasTraductor1("SI"), Cliente.Preferencias1.SI)

    def test_preferencias1_none(self):
        self.assertEqual(preferenciasTraductor1(None), Cliente.Preferencias1.NO)

    def test_preferencias2_si(self):
        self.assertEqual(preferenciasTraductor2("si"), Cliente.Preferencias2.SI)

    def test_preferencias2_indiferente(self):
        self.assertEqual(preferenciasTraductor2("indiferente"), Cliente.Preferencias2.IND)

    def test_preferencias2_none(self):
        self.assertEqual(preferenciasTraductor2(None), Cliente.Preferencias2.IND)


class EstadoPropTradTests(TestCase):
    def test_vendido(self):
        self.assertEqual(estadoPropTrad("vendido"), Propiedad.estadoPiso.VENDIDO)

    def test_a_la_venta(self):
        self.assertEqual(estadoPropTrad("a la venta"), Propiedad.estadoPiso.ACTIVO)

    def test_con_guiones_bajos(self):
        self.assertEqual(estadoPropTrad("a_la_venta"), Propiedad.estadoPiso.ACTIVO)

    def test_no_oficial(self):
        self.assertEqual(estadoPropTrad("no es oficial"), Propiedad.estadoPiso.NoOficial)

    def test_valor_desconocido(self):
        self.assertEqual(estadoPropTrad("pendiente"), Propiedad.estadoPiso.NoOficial)


class GuardadorURLTests(TestCase):
    def test_lista_valida(self):
        data = [{"url": "http://img1.jpg"}, {"url": "http://img2.jpg"}]
        self.assertEqual(guardadorURL(data), ["http://img1.jpg", "http://img2.jpg"])

    def test_lista_con_items_sin_url(self):
        data = [{"url": "http://img1.jpg"}, {"name": "img2"}]
        self.assertEqual(guardadorURL(data), ["http://img1.jpg"])

    def test_valor_none(self):
        self.assertEqual(guardadorURL(None), [])

    def test_valor_null_string(self):
        self.assertEqual(guardadorURL("null"), [])

    def test_valor_no_lista(self):
        self.assertEqual(guardadorURL("string"), [])


# =============================================================================
# TESTS PARA MATCHING
# =============================================================================

class MatchingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.agencia = Agencia.objects.create(
            location_id="test-agency-123",
            nombre="Agencia Test",
            active=True
        )

        cls.provincia = Provincia.objects.create(nombre="Barcelona")
        cls.municipio = Municipio.objects.create(
            nombre="Cornella",
            provincia=cls.provincia
        )
        cls.zona = Zona.objects.create(
            nombre="Almeda",
            municipio=cls.municipio
        )

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

        # Propiedad sin zona para testear el caso edge
        cls.propiedad_sin_zona = Propiedad.objects.create(
            agencia=cls.agencia,
            ghl_contact_id="prop-002",
            precio=Decimal("150000.00"),
            habitaciones=2,
            metros=60,
            estado=Propiedad.estadoPiso.ACTIVO,
            zona=None,
        )

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

        cls.cliente_no_match = Cliente.objects.create(
            agencia=cls.agencia,
            ghl_contact_id="cli-002",
            nombre="Cliente No Match",
            presupuesto_maximo=Decimal("100000.00"),
            habitaciones_minimas=2,
            metrosMinimo=80,
            animales=Cliente.Preferencias1.NO,
            balcon=Cliente.Preferencias2.IND,
            garaje=Cliente.Preferencias2.IND,
            patioInterior=Cliente.Preferencias2.IND
        )
        cls.cliente_no_match.zona_interes.add(cls.zona)

    def test_buscar_clientes_para_propiedad_encuentra_match(self):
        clientes = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        self.assertIn(self.cliente_match, clientes)

    def test_buscar_clientes_para_propiedad_excluye_no_match(self):
        clientes = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        self.assertNotIn(self.cliente_no_match, clientes)

    def test_buscar_clientes_para_propiedad_sin_zona_retorna_vacio(self):
        """Propiedad sin zona no debe matchear con ningun cliente"""
        clientes = buscar_clientes_para_propiedad(self.propiedad_sin_zona, self.agencia)
        self.assertEqual(clientes.count(), 0)

    def test_buscar_propiedades_para_cliente(self):
        propiedades = buscar_propiedades_para_cliente(self.cliente_match, self.agencia)
        self.assertIn(self.propiedad, propiedades)

    def test_actualizar_relaciones_propiedad(self):
        clientes = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        count = actualizar_relaciones_propiedad(self.propiedad, clientes)
        self.assertGreater(count, 0)
        self.assertIn(self.propiedad, self.cliente_match.propiedades_interes.all())

    def test_actualizar_relaciones_cliente(self):
        propiedades = buscar_propiedades_para_cliente(self.cliente_match, self.agencia)
        count = actualizar_relaciones_cliente(self.cliente_match, propiedades)
        self.assertGreater(count, 0)

    def test_set_reemplaza_relaciones_existentes(self):
        """Verificar que .set() reemplaza relaciones previas correctamente"""
        # Primer matching
        clientes1 = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        actualizar_relaciones_propiedad(self.propiedad, clientes1)
        count1 = self.propiedad.interesados.count()

        # Segundo matching (mismo resultado)
        clientes2 = buscar_clientes_para_propiedad(self.propiedad, self.agencia)
        actualizar_relaciones_propiedad(self.propiedad, clientes2)
        count2 = self.propiedad.interesados.count()

        # No debe haber duplicados
        self.assertEqual(count1, count2)


# =============================================================================
# TESTS PARA API PUBLICA
# =============================================================================

class HealthCheckAPITests(APITestCase):
    def test_health_check_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)

    def test_health_check_contains_database_status(self):
        response = self.client.get('/')
        self.assertIn('checks', response.data)
        self.assertIn('database', response.data['checks'])


class ZonasAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.provincia = Provincia.objects.create(nombre="Madrid")
        cls.municipio = Municipio.objects.create(
            nombre="Madrid Centro",
            provincia=cls.provincia
        )
        cls.zona = Zona.objects.create(
            nombre="Chamberi",
            municipio=cls.municipio
        )

    def test_get_zonas_tree_returns_200(self):
        client = HttpClient()
        response = client.get('/zonas/')
        self.assertEqual(response.status_code, 200)

    def test_get_zonas_tree_contains_data(self):
        client = HttpClient()
        response = client.get('/zonas/')
        data = response.json()
        self.assertIn('zonas', data)
        self.assertEqual(len(data['zonas']), 1)
        self.assertEqual(data['zonas'][0]['provincia'], 'Madrid')
