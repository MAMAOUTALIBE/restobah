"""Account links use configured origins, never a visitor-controlled Host header."""
from urllib.parse import urlencode, urlsplit

from django.conf import settings

from .production_readiness import probe_smtp, probe_url, smtp_configured
from .public_details import public_url


PRIVATE_EMAIL_BACKENDS = {
    'shop.email_backend.PrivateFileEmailBackend',
    'django.core.mail.backends.locmem.EmailBackend',
}


def frontend_base_url():
    value = settings.FRONTEND_URL
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 33 for char in value):
        raise ValueError('Origine du site invalide.')
    try:
        parts = urlsplit(value)
        if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
            raise ValueError('Une origine sans chemin, identifiants ni paramètres est requise.')
        local = (parts.scheme in {'http', 'https'} and parts.hostname in {'localhost', '127.0.0.1', '::1'}
                 and (parts.port is None or 1 <= parts.port <= 65535))
        private_delivery = settings.DEBUG or settings.EMAIL_BACKEND in PRIVATE_EMAIL_BACKENDS
        if not (local and private_delivery) and not public_url(value):
            raise ValueError('Une origine HTTPS publique est requise.')
    except (ValueError, UnicodeError) as error:
        raise ValueError('Origine du site invalide.') from error
    return value.rstrip('/')


def password_reset_link(uid, token):
    return frontend_base_url() + '/?' + urlencode({'reset_uid': uid, 'reset_token': token})


def password_reset_available():
    try:
        frontend_base_url()
    except ValueError:
        return False
    # Private file/in-memory delivery is useful in development, not a claim
    # that customers can receive messages from a production server.
    return bool(settings.DEBUG or (public_url(settings.FRONTEND_URL) and smtp_configured()))


def account_delivery_report(*, check_url=False, smtp_check=False):
    origin_ready = False
    try:
        origin_ready = bool(public_url(frontend_base_url()))
    except ValueError:
        pass
    smtp_ready = bool(smtp_configured())
    checks = [
        {'id': 'frontend_origin', 'status': 'pass' if origin_ready else 'blocker',
         'message': 'Origine HTTPS publique configurée.' if origin_ready else 'Renseigner FRONTEND_URL avec l’origine HTTPS publique du site, sans chemin ni paramètres.'},
        {'id': 'smtp_configuration', 'status': 'pass' if smtp_ready else 'blocker',
         'message': 'Configuration SMTP chiffrée et authentifiée renseignée.' if smtp_ready else 'Configurer un fournisseur SMTP, ses identifiants privés, un expéditeur réel et un seul mode TLS ou SSL.'},
    ]
    external = {'siteHttps': 'not_checked', 'smtpConnection': 'not_checked', 'emailDelivery': 'not_checked'}
    if check_url:
        passed = bool(origin_ready and probe_url(frontend_base_url() + '/'))
        external['siteHttps'] = 'pass' if passed else 'failed'
        checks.append({'id': 'frontend_https', 'status': 'pass' if passed else 'blocker',
                       'message': 'Site HTTPS joignable avec certificat valide.' if passed else 'Vérifier le DNS, le certificat et la réponse HTTPS directe du site.'})
    if smtp_check:
        try:
            passed = bool(smtp_ready and probe_smtp())
        except Exception:
            passed = False
        external['smtpConnection'] = 'pass' if passed else 'failed'
        checks.append({'id': 'smtp_connection', 'status': 'pass' if passed else 'blocker',
                       'message': 'Connexion SMTP authentifiée réussie, aucun message envoyé.' if passed else 'Connexion SMTP non vérifiée ; contrôler la configuration privée.'})
    return {'configurationReady': all(row['status'] == 'pass' for row in checks),
            'scope': 'account_delivery_configuration_and_selected_read_only_probes',
            'checks': checks, 'externalChecks': external,
            'limitation': 'Une connexion SMTP réussie ne prouve pas la réception : contrôler ensuite un vrai message sur une adresse choisie pour la recette.'}
