import secrets
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError

class Command(BaseCommand):
    help='Crée un administrateur local de démonstration et écrit ses accès dans un fichier privé.'
    def handle(self,*args,**options):
        if not settings.DEBUG:
            raise CommandError('Cette commande est réservée au développement local.')
        target=settings.RUNTIME_DIR/'admin-credentials.txt'
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        email='admin@stc.local'
        User=get_user_model()
        if User.objects.filter(email=email).exists():
            self.stdout.write('Administrateur local déjà présent ; mot de passe conservé.')
            return
        password=secrets.token_urlsafe(24)
        User.objects.create_superuser(email=email,password=password,first_name='Équipe STC')
        target.write_text(f'Administration locale : http://localhost:8000/admin/\nE-mail : {email}\nMot de passe : {password}\n')
        target.chmod(0o600)
        self.stdout.write(f'Administrateur créé. Accès disponibles dans {target} (fichier privé).')
