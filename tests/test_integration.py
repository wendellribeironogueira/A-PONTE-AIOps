import os
import subprocess
import time
from pathlib import Path

import pytest

# Configuração
TEST_PROJECT_NAME = "integration-test-proj"


def run_cli(command, env=None):
    """Executa um comando aponte e retorna o resultado."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    # Força modo não interativo para scripts que suportam
    full_env["FORCE_NON_INTERACTIVE"] = "true"
    # Injeta e-mail de segurança obrigatório para criação de projetos
    full_env["TF_VAR_security_email"] = "ci-test@aponte.platform"

    # Resolve o caminho absoluto do binário 'aponte'
    # Assume que o teste está rodando na raiz ou que bin/aponte existe
    root = Path(__file__).parent.parent
    bin_path = root / "bin" / "aponte"

    result = subprocess.run(
        f"{bin_path} {command}", shell=True, capture_output=True, text=True, env=full_env
    )
    return result


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    """Garante limpeza antes e depois dos testes."""
    # Setup: Tenta destruir se existir de testes anteriores
    run_cli(f"project destroy {TEST_PROJECT_NAME}")
    yield
    # Teardown: Destroi após o teste
    run_cli(f"project destroy {TEST_PROJECT_NAME}")


def test_project_lifecycle():
    """
    Testa o ciclo de vida completo de um projeto:
    Criar -> Listar -> Alternar -> Destruir
    """
    print(f"\n🚀 Iniciando teste de ciclo de vida para: {TEST_PROJECT_NAME}")

    # 1. CRIAÇÃO
    print("   [1/4] Criando projeto...")
    res_create = run_cli(f"project create {TEST_PROJECT_NAME}")
    assert res_create.returncode == 0, f"Falha ao criar: {res_create.stderr}"
    assert "Projeto criado" in res_create.stdout

    # 2. LISTAGEM
    print("   [2/4] Listando projetos...")
    res_list = run_cli("project list")
    assert res_list.returncode == 0
    assert TEST_PROJECT_NAME in res_list.stdout

    # 3. ALTERNÂNCIA
    print("   [3/4] Alternando contexto...")
    res_switch = run_cli(f"project switch {TEST_PROJECT_NAME}")
    assert res_switch.returncode == 0
    print(f"   Output do switch: {res_switch.stdout}")
    assert f"contexto alterado para: {TEST_PROJECT_NAME}" in res_switch.stdout

    # 4. DESTROY é tratado pelo fixture cleanup, mas podemos testar explicitamente se quisermos
    # O fixture rodará ao final.
