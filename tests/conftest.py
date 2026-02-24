import os
import sys
from pathlib import Path

import pytest

# Garante que o diretório raiz do projeto esteja no PYTHONPATH
# Isso permite importar 'core.agents', 'core.lib', etc. nos testes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(scope="session")
def project_root():
    """Retorna o caminho absoluto para a raiz do projeto A-PONTE."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def mock_aws_credentials():
    """Define credenciais fake para testes que usam boto3/moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
