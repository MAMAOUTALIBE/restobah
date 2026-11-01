"""Read-only configuration checks. This is not a commercial acceptance certificate."""
import ipaddress
import json
import re
import socket
import subprocess
import sys
from email.utils import parseaddr
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.conf import settings
from django.core.mail import get_connection
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from .models import Product, Restaurant, User
from .public_details import public_details, public_email, public_host, public_url


def check_item(key, passed, success, failure):
    return {'id': key, 'status': 'pass' if passed else 'blocker', 'message': success if passed else failure}


def database_status():
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    executor = MigrationExecutor(connection)
    pending = bool(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    return [
        check_item('database', connection.vendor == 'postgresql', 'PostgreSQL joignable.', 'PostgreSQL requis pour cette configuration de livraison.'),
        check_item('migrations', not pending, 'Migrations appliquées.', 'Des migrations restent à appliquer.'),
    ]


def content_status():
    restaurant = Restaurant.objects.filter(pk=1).first()  # Never get_or_create here.
    present = bool(restaurant and all(str(value).strip() for value in (restaurant.name, restaurant.address, restaurant.city)))
    results = [check_item('restaurant', present, 'Identité et adresse renseignées.', 'Identité et adresse du restaurant à renseigner.')]
    service = bool(restaurant and (restaurant.pickup_enabled or (restaurant.delivery_enabled and restaurant.delivery_postal_codes)))
    results.append(check_item('services', service, 'Au moins un service configuré.', 'Configurer le retrait ou une zone de livraison.'))
    hours = bool(restaurant and restaurant.opening_hours.exists())
    results.append(check_item('hours', hours, 'Créneaux horaires présents.', 'Horaires réels à renseigner.'))
    products = Product.objects.filter(available=True).exists()
    results.append(check_item('catalogue', products, 'Des plats disponibles sont présents.', 'Aucun plat disponible.'))
    results.append(check_item('content_approved', settings.STC_CONTENT_APPROVED,
                              'Validation des contenus déclarée par le responsable.',
                              'Le client doit valider identité, carte, photos, prix, allergènes, horaires, zones et documents ; STC_CONTENT_APPROVED=0.'))
    return results


def staff_status():
    staff = list(User.objects.filter(is_active=True, is_staff=True))
    def shared(user):
        local = user.email.partition('@')[0].lower()
        return bool(re.search(r'(^|[._+\-])(demo|demonstration|test)([._+\-]|$)', local)) or not public_email(user.email)
    demo = any(shared(user) for user in staff)
    permissions = ['shop.view_order', 'shop.change_order', 'shop.record_onsite_payment']
    nominal = any(not shared(user) and user.first_name.strip() and user.last_name.strip()
                  and user.has_usable_password() and user.has_perms(permissions) for user in staff)
    return [
        check_item('shared_demo_staff', not demo, 'Aucun compte de démonstration actif détecté dans le personnel.',
                   'Désactiver les comptes de personnel partagés de démonstration avant l’ouverture commerciale.'),
        check_item('financial_staff', nominal, 'Un compte nominatif actif possède les droits de règlement sur place.',
                   'Créer un compte nominatif avec prénom, nom et droits explicites de consultation, modification et règlement des commandes.'),
    ]


def smtp_configured():
    sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    credentials = all(value and not value.upper().startswith('REPLACE') for value in
                      (settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD))
    return (settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
            and public_host(settings.EMAIL_HOST) and credentials
            and 1 <= settings.EMAIL_PORT <= 65535
            and bool(settings.EMAIL_USE_TLS) != bool(getattr(settings, 'EMAIL_USE_SSL', False))
            and bool(public_email(sender)))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_url(url):
    """Only configured public HTTPS URLs; do not follow redirects to private services."""
    try:
        if not public_url(url):
            return False
        addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            return False
        request = Request(url, headers={'User-Agent': 'STC-readiness/1', 'Range': 'bytes=0-0'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=8) as response:
            return 200 <= response.status < 300
    except (OSError, ValueError, HTTPError):
        return False


def probe_smtp():
    # open() performs connection, STARTTLS and authentication. Never send_messages().
    backend = get_connection(fail_silently=False)
    try:
        return bool(backend.open())
    finally:
        backend.close()


def backup_status(directory, project, max_age):
    candidates = [settings.BASE_DIR / 'scripts' / 'backup.py', settings.BASE_DIR.parent / 'scripts' / 'backup.py']
    script = next((path for path in candidates if path.is_file()), None)
    if not script:
        return False
    try:
        result = subprocess.run([sys.executable, str(script), '--check-freshness', str(max_age),
                                 '--project-name', project, '--directory', str(directory)],
                                capture_output=True, text=True, timeout=45, check=False)
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
        return result.returncode == 0 and isinstance(payload, dict) and payload.get('status') == 'ok'
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def production_report(*, check_urls=False, smtp_check=False, backup_directory=None, backup_project='stc', backup_max_age=26):
    checks = [
        check_item('debug', not settings.DEBUG, 'DEBUG désactivé.', 'Désactiver DEBUG.'),
        check_item('secret_key', len(settings.SECRET_KEY) >= 50 and len(set(settings.SECRET_KEY)) >= 5
                   and not settings.SECRET_KEY.startswith(('REPLACE', 'django-insecure-')),
                   'Clé Django de longueur suffisante, sans marqueur de remplacement.',
                   'Configurer une clé Django privée et aléatoire ; ne pas conserver une valeur d’exemple.'),
        check_item('demo', not settings.DEMO_MODE, 'Mode démonstration désactivé.', 'Le mode démonstration est encore actif.'),
        check_item('payment_mode', settings.PAYMENT_MODE == 'on_site', 'Règlement sur place configuré.', 'Cette livraison exige le mode on_site.'),
    ]
    public = public_details()
    frontend = public_url(settings.FRONTEND_URL)
    host = urlsplit(frontend).hostname if frontend else None
    hosts = [value.strip() for value in settings.ALLOWED_HOSTS]
    origins = [value.rstrip('/') for value in settings.CSRF_TRUSTED_ORIGINS]
    # Compose health checks use these exact internal hosts. The public frontend
    # domain remains mandatory; no wildcard, suffix or other alias is accepted.
    permitted_hosts = {host, 'backend', 'localhost', '127.0.0.1'}
    tls = bool(frontend and host in hosts and all(value in permitted_hosts for value in hosts)
               and settings.FRONTEND_URL.rstrip('/') in origins and settings.SECURE_SSL_REDIRECT
               and settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE)
    checks.append(check_item('https_hosts', tls, 'Origine HTTPS, hôtes et cookies sécurisés configurés.',
                             'Configurer le domaine HTTPS exact, les hôtes autorisés, CSRF, la redirection et les cookies sécurisés.'))
    for key, title in [('contactPhone', 'Téléphone'), ('contactEmail', 'E-mail de contact'),
                       ('legalNoticeUrl', 'Mentions légales'), ('privacyUrl', 'Confidentialité'), ('termsUrl', 'Conditions de commande')]:
        checks.append(check_item(key, bool(public[key]), f'{title} renseigné(es).', f'{title} absent(es) ou invalide(s).'))
    try:
        checks.extend(database_status())
        checks.extend(content_status())
        checks.extend(staff_status())
    except Exception:
        # A DB/config error can contain credentials or SQL. Never reflect the exception.
        checks.append(check_item('database_access', False, '', 'Base ou schéma illisible ; vérifier les journaux privés.'))
    mail_ready = smtp_configured()
    recipients = settings.ORDER_NOTIFICATION_EMAILS
    checks.append(check_item('smtp_config', mail_ready, 'SMTP chiffré et authentifié configuré.', 'Renseigner SMTP chiffré, authentifiants privés et expéditeur réel.'))
    checks.append(check_item('team_notifications', bool(recipients) and all(public_email(value) for value in recipients),
                             'Destinataires des alertes équipe renseignés.', 'Renseigner des destinataires réels pour les alertes de commande.'))
    directory = Path(backup_directory) if backup_directory is not None else settings.BASE_DIR.parent / 'backups'
    fresh = backup_status(directory, backup_project, backup_max_age)
    checks.append(check_item('backup_freshness', fresh, 'Sauvegarde complète récente vérifiée par le CLI dédié.',
                             'Sauvegarde complète récente non vérifiée ; préciser le dossier privé monté en lecture seule.'))
    external = {'https': 'not_checked', 'smtpConnection': 'not_checked', 'emailDelivery': 'not_checked', 'offsiteBackup': 'not_checked'}
    if check_urls:
        urls = [frontend, public['legalNoticeUrl'], public['privacyUrl'], public['termsUrl']]
        verified = all(bool(value) and probe_url(value) for value in urls)
        external['https'] = 'pass' if verified else 'failed'
        checks.append(check_item('https_probe', verified, 'URLs HTTPS accessibles en réponse directe 2xx, certificat vérifié.',
                                 'Contrôle HTTPS refusé ou en échec ; vérifier DNS, certificat et liens directs.'))
    if smtp_check:
        try:
            verified = mail_ready and probe_smtp()
        except Exception:
            verified = False
        external['smtpConnection'] = 'pass' if verified else 'failed'
        checks.append(check_item('smtp_probe', verified, 'Connexion, chiffrement et authentification SMTP réussis ; aucun e-mail envoyé.',
                                 'Connexion SMTP non vérifiée ou refusée ; consulter les journaux privés.'))
    return {'configurationReady': not any(item['status'] == 'blocker' for item in checks),
            'scope': 'configuration_and_selected_read_only_probes', 'checks': checks, 'externalChecks': external,
            'limitations': [
                'Un résultat favorable ne constitue pas une acceptation commerciale ni une certification de caisse.',
                'La réception réelle des e-mails doit être contrôlée séparément par le responsable.',
                'La présence, le chiffrement et la restauration d’une copie extérieure ne sont pas prouvés par ce contrôle de fraîcheur.',
                'La validation déclarée des contenus et les comptes nominatifs doivent être confirmés avec le client.',
            ]}
