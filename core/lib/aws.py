import os
from typing import Optional

import boto3
from botocore.config import Config

# Configuração de Retries (ADR-013)
# Modo 'adaptive' é ideal para scripts de automação que podem sofrer throttling
# Ele implementa Exponential Backoff com Jitter automaticamente.
DEFAULT_CONFIG = Config(
    retries={"max_attempts": 10, "mode": "adaptive"},
    connect_timeout=10,
    read_timeout=30,
    user_agent_extra="A-PONTE-Platform/3.0 (AI-Ops)",  # Rastreabilidade no CloudTrail
)

AI_HISTORY_TABLE = "a-ponte-ai-history"
EVENTS_DEDUP_TABLE = "a-ponte-events-dedup"
REGISTRY_TABLE = "a-ponte-registry"


def get_region() -> str:
    """Retorna a região AWS configurada no ambiente."""
    return (
        os.getenv("AWS_REGION")
        or os.getenv("TF_VAR_aws_region")
        or "sa-east-1"
    )


def get_session(
    project_name: Optional[str] = None, region_name: Optional[str] = None
) -> boto3.Session:
    """
    Retorna uma sessão Boto3 configurada e resiliente.

    Args:
        project_name: (Futuro) Usado para assumir a role específica do projeto.
        region_name: Região AWS (default: env var ou sa-east-1).
    """
    # 1. Determina a região com fallback seguro
    region = region_name or get_region()

    # 2. Cria sessão base (usa credenciais do ambiente/perfil ~/.aws/credentials)
    session = boto3.Session(region_name=region)

    return session


def get_client(service_name: str, session: Optional[boto3.Session] = None) -> boto3.client:
    """
    Factory de clientes AWS com configuração de resiliência padrão.
    """
    sess = session or get_session()
    return sess.client(service_name, config=DEFAULT_CONFIG)


def get_resource(service_name: str, session: Optional[boto3.Session] = None) -> boto3.resource:
    """
    Factory de resources AWS com configuração de resiliência padrão.
    """
    sess = session or get_session()
    return sess.resource(service_name, config=DEFAULT_CONFIG)


def get_current_user() -> str:
    """Retorna o usuário atual do sistema."""
    return os.getenv("USER") or os.getenv("USERNAME") or "default"


def get_account_id() -> str:
    """Retorna o Account ID da AWS."""
    try:
        return get_client("sts").get_caller_identity()["Account"]
    except Exception:
        return "unknown"
