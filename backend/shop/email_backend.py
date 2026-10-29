from pathlib import Path
from django.core.mail.backends.filebased import EmailBackend

class PrivateFileEmailBackend(EmailBackend):
    """Development-only messages remain readable by the current OS account only."""
    def send_messages(self,email_messages):
        sent=super().send_messages(email_messages)
        for message in Path(self.file_path).glob('*.log'):
            message.chmod(0o600)
        return sent
