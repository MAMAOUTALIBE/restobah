import json
import math
import re

from django.core.management.base import BaseCommand, CommandError

from shop.production_readiness import production_report


class Command(BaseCommand):
    help = 'Contrôle de configuration de livraison en lecture seule ; aucun e-mail ni écriture métier.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')
        parser.add_argument('--check-urls', action='store_true', help='Vérifier les URLs HTTPS publiques sans suivre les redirections.')
        parser.add_argument('--smtp-check', action='store_true', help='Connexion et authentification seulement ; aucun e-mail envoyé.')
        parser.add_argument('--backup-directory', help='Dossier de sauvegardes privées accessible en lecture seule.')
        parser.add_argument('--backup-project', default='stc')
        parser.add_argument('--backup-max-age', type=float, default=26, help='Âge maximal en heures, 26 par défaut.')

    def handle(self, *args, **options):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', options['backup_project']) or not (
                math.isfinite(options['backup_max_age']) and 0 < options['backup_max_age'] <= 24 * 366):
            raise CommandError('Paramètres de contrôle de sauvegarde invalides.')
        report = production_report(check_urls=options['check_urls'], smtp_check=options['smtp_check'],
                                   backup_directory=options['backup_directory'], backup_project=options['backup_project'],
                                   backup_max_age=options['backup_max_age'])
        if options['as_json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            for check in report['checks']:
                self.stdout.write(f"{check['status'].upper()} [{check['id']}] {check['message']}")
            self.stdout.write('Contrôles externes : ' + json.dumps(report['externalChecks'], ensure_ascii=False))
            for limitation in report['limitations']:
                self.stdout.write(limitation)
        if not report['configurationReady']:
            raise CommandError('Configuration incomplète : consulter les blocages du rapport.', returncode=1)
