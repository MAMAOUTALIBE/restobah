from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections

from shop.sequences import repair_crm_sequences


class Command(BaseCommand):
    help = 'Avance les séquences plats/restaurant sans modifier ni recréer les données.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default=DEFAULT_DB_ALIAS, choices=tuple(connections))

    def handle(self, *args, **options):
        using = options['database']
        changed = repair_crm_sequences(using)
        if connections[using].vendor == 'postgresql':
            message = f'Séquences vérifiées : {changed} compteur(s) avancé(s). Aucune donnée modifiée.'
        else:
            message = 'Compteurs gérés automatiquement par la base. Aucune donnée modifiée.'
        self.stdout.write(self.style.SUCCESS(message))
