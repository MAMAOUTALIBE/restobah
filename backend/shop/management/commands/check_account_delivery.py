import json

from django.core.management.base import BaseCommand, CommandError

from shop.account_links import account_delivery_report


class Command(BaseCommand):
    help = 'Contrôle les liens de compte et la configuration e-mail sans envoi ni écriture métier.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')
        parser.add_argument('--check-url', action='store_true', help='Vérifier DNS, certificat et réponse HTTPS du site.')
        parser.add_argument('--smtp-check', action='store_true', help='Connexion/authentification seulement ; aucun e-mail envoyé.')

    def handle(self, *args, **options):
        report = account_delivery_report(check_url=options['check_url'], smtp_check=options['smtp_check'])
        if options['as_json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            for row in report['checks']:
                self.stdout.write(f"{row['status'].upper()} [{row['id']}] {row['message']}")
            self.stdout.write(report['limitation'])
        if not report['configurationReady']:
            raise CommandError('Envoi de récupération non configuré ; consulter les blocages.', returncode=1)
