"""Explicit, validated allow-list of information intended for the public site."""
import ipaddress
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email


def public_host(host):
    host = (host or '').lower().rstrip('.')
    if not host or host == 'localhost' or '.' not in host:
        return False
    if host in {'example.com', 'example.org', 'example.net'} or host.endswith(
            ('.example', '.example.com', '.example.org', '.example.net', '.invalid', '.test', '.localhost', '.local')):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        try:
            ascii_host = host.encode('idna').decode('ascii')
        except UnicodeError:
            return False
        return len(ascii_host) <= 253 and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                             for label in ascii_host.split('.'))


def public_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        return ''
    try:
        URLValidator(schemes=['https'])(value)
        parts = urlsplit(value)
        if parts.username or parts.password or parts.port not in (None, 443) or not public_host(parts.hostname):
            return ''
    except (ValidationError, ValueError):
        return ''
    return value


def public_email(value):
    if not isinstance(value, str) or len(value) > 254:
        return ''
    try:
        validate_email(value)
    except ValidationError:
        return ''
    return value if public_host(value.rsplit('@', 1)[-1]) else ''


def public_phone(value):
    if not isinstance(value, str) or not re.fullmatch(r'\+?[0-9 () .-]{8,40}', value):
        return ''
    return value if 8 <= len(re.sub(r'\D', '', value)) <= 15 else ''


def public_details():
    # Never serialize settings, os.environ, approval flags or mail credentials.
    return {
        'contactPhone': public_phone(settings.STC_CONTACT_PHONE),
        'contactEmail': public_email(settings.STC_CONTACT_EMAIL),
        'legalNoticeUrl': public_url(settings.STC_LEGAL_NOTICE_URL),
        'privacyUrl': public_url(settings.STC_PRIVACY_URL),
        'termsUrl': public_url(settings.STC_TERMS_URL),
    }
