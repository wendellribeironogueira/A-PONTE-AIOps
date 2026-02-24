import re


class InputSanitizer:
    """
    Remove segredos e dados sensíveis de strings antes de enviar para LLMs externos.
    Garante a soberania dos dados conforme ADR-016 e ADR-029.
    """

    # Padrões de Regex para Redação (Redaction)
    PATTERNS = [
        # AWS Access Keys (AKIA...)
        (r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])", "[AWS_ACCESS_KEY_REDACTED]"),
        # AWS Secret Keys (Tentativa heurística de capturar strings de 40 chars base64-like após 'key')
        (
            r'(?i)(aws_secret_access_key|secret_key|secret)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?',
            r"\1: [REDACTED]",
        ),
        # GitHub Tokens (ghp_)
        (r"ghp_[a-zA-Z0-9]{36}", "[GITHUB_TOKEN_REDACTED]"),
        # Private Keys (RSA/PEM)
        (r"-----BEGIN [A-Z]+ PRIVATE KEY-----", "[PRIVATE_KEY_REDACTED]"),
        # Senhas genéricas em connection strings ou variáveis
        (
            r'(?i)(password|passwd|pwd|db_pass)\s*[:=]\s*["\']?([^;&\s"\']{6,})["\']?',
            r"\1=[REDACTED]",
        ),
        # Endereços de Email (Opcional, para privacidade)
        (r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "[EMAIL_REDACTED]"),
        # Google API Key (AIza...)
        (r"AIza[0-9A-Za-z\-_]{35}", "[GOOGLE_API_KEY_REDACTED]"),
    ]

    @staticmethod
    def clean(text: str) -> str:
        """Higieniza o texto aplicando todas as regras de redação."""
        if not text:
            return ""
        cleaned = text
        for pattern, replacement in InputSanitizer.PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned)
        return cleaned
