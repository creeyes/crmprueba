"""
Management command para sincronizar registros locales (sin ghl_contact_id) con GHL.
Maneja registros insertados via SQL que bypasearon Django signals.

Uso:
  python manage.py sync_to_ghl                     # Sync todo pendiente
  python manage.py sync_to_ghl --type cliente       # Solo clientes
  python manage.py sync_to_ghl --type propiedad     # Solo propiedades
  python manage.py sync_to_ghl --location-id X      # Solo una agencia
  python manage.py sync_to_ghl --batch-size 50      # Procesar en lotes de 50
  python manage.py sync_to_ghl --retry-errors       # Reintentar errores previos
  python manage.py sync_to_ghl --dry-run            # Mostrar sin ejecutar
"""
import logging
from django.core.management.base import BaseCommand
from django.db.models import Q

from ghl_middleware.models import Cliente, Propiedad, Agencia
from ghl_middleware.utils import sync_record_to_ghl, rate_limit_wait

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sincroniza registros locales (sin ghl_contact_id) con GHL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            choices=['cliente', 'propiedad', 'all'],
            default='all',
            help='Tipo de registro a sincronizar (default: all)'
        )
        parser.add_argument(
            '--location-id',
            type=str,
            default=None,
            help='Sincronizar solo registros de esta agencia (location_id)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Numero maximo de registros a procesar (default: 100)'
        )
        parser.add_argument(
            '--retry-errors',
            action='store_true',
            help='Reintentar registros con sync_status=error'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar que se sincronizaria sin hacer cambios'
        )

    def handle(self, *args, **options):
        record_type = options['type']
        location_id = options['location_id']
        batch_size = options['batch_size']
        retry_errors = options['retry_errors']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('--- MODO DRY-RUN: No se haran cambios ---'))

        # Filtro base: registros pendientes de sync
        sync_filter = Q(sync_status='pending')

        # Tambien capturar registros con ghl_contact_id=NULL que fueron
        # insertados via SQL sin establecer sync_status='pending'
        sync_filter |= Q(ghl_contact_id__isnull=True)
        sync_filter |= Q(ghl_contact_id='')

        if retry_errors:
            sync_filter |= Q(sync_status='error')

        # Filtro por agencia si se especifica
        agencia_filter = Q()
        if location_id:
            agencia_filter = Q(agencia__location_id=location_id)
            # Verificar que la agencia existe y esta activa
            if not Agencia.objects.filter(location_id=location_id, active=True).exists():
                self.stdout.write(self.style.ERROR(
                    f'Agencia {location_id} no encontrada o no esta activa'
                ))
                return

        stats = {
            'clientes_ok': 0, 'clientes_fail': 0,
            'propiedades_ok': 0, 'propiedades_fail': 0
        }

        # --- Sincronizar Clientes ---
        if record_type in ('all', 'cliente'):
            clientes = Cliente.objects.filter(
                sync_filter & agencia_filter,
                agencia__active=True
            ).select_related('agencia')[:batch_size]

            count = clientes.count()
            self.stdout.write(f'Clientes pendientes de sync: {count}')

            if not dry_run:
                for i, cliente in enumerate(clientes, 1):
                    self.stdout.write(f'  [{i}/{count}] Sincronizando Cliente PK={cliente.pk} "{cliente.nombre}"...')
                    success = sync_record_to_ghl(cliente, 'cliente')
                    if success:
                        stats['clientes_ok'] += 1
                        self.stdout.write(self.style.SUCCESS(f'    -> OK (GHL ID: {cliente.ghl_contact_id})'))
                    else:
                        stats['clientes_fail'] += 1
                        self.stdout.write(self.style.ERROR(f'    -> FALLO: {cliente.sync_error}'))
                    rate_limit_wait(default_wait=0.3)

        # --- Sincronizar Propiedades ---
        if record_type in ('all', 'propiedad'):
            propiedades = Propiedad.objects.filter(
                sync_filter & agencia_filter,
                agencia__active=True
            ).select_related('agencia', 'zona')[:batch_size]

            count = propiedades.count()
            self.stdout.write(f'Propiedades pendientes de sync: {count}')

            if not dry_run:
                for i, propiedad in enumerate(propiedades, 1):
                    self.stdout.write(f'  [{i}/{count}] Sincronizando Propiedad PK={propiedad.pk} (zona: {propiedad.zona})...')
                    success = sync_record_to_ghl(propiedad, 'propiedad')
                    if success:
                        stats['propiedades_ok'] += 1
                        self.stdout.write(self.style.SUCCESS(f'    -> OK (GHL ID: {propiedad.ghl_contact_id})'))
                    else:
                        stats['propiedades_fail'] += 1
                        self.stdout.write(self.style.ERROR(f'    -> FALLO: {propiedad.sync_error}'))
                    rate_limit_wait(default_wait=0.3)

        # --- Resumen ---
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Sync completado: '
            f'Clientes OK={stats["clientes_ok"]} FAIL={stats["clientes_fail"]} | '
            f'Propiedades OK={stats["propiedades_ok"]} FAIL={stats["propiedades_fail"]}'
        ))
