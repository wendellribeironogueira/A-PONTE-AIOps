import logging
import os
from pathlib import Path

import pytest
import tftest

logger = logging.getLogger(__name__)


def get_terraform_modules():
    """
    Descobre dinamicamente módulos Terraform/Terragrunt no projeto.
    Procura em 'modules/' e 'infrastructure/'.
    """
    root = Path(__file__).parent.parent.parent
    search_paths = [root / "modules", root / "infrastructure"]
    modules = []

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Itera sobre subdiretórios procurando por arquivos .tf ou terragrunt.hcl
        for item in search_path.iterdir():
            if item.is_dir():
                if (item / "main.tf").exists() or (item / "terragrunt.hcl").exists():
                    modules.append(str(item))

    return modules


@pytest.mark.parametrize("module_path", get_terraform_modules())
def test_iac_plan_integrity(module_path):
    """
    Teste Funcional: Executa 'init' e 'plan' em cada módulo detectado.
    Isso valida sintaxe, referências de variáveis e integridade do provider.
    """
    path_obj = Path(module_path)

    # Detecta se deve usar Terragrunt ou Terraform puro
    binary = "terraform"
    if (path_obj / "terragrunt.hcl").exists():
        binary = "terragrunt"

    logger.info(f"Testando módulo: {path_obj.name} com {binary}")

    try:
        # Inicializa o wrapper do tftest
        tf = tftest.TerraformTest(
            path_obj.name, basedir=str(path_obj.parent), binary=binary
        )

        # Setup (Init) com limpeza automática
        tf.setup(cleanup_on_exit=True)

        # Executa o Plan e captura o output
        plan = tf.plan(output=True)

        # Asserções Básicas
        assert (
            plan.outputs is not None
        ), "O plano não gerou outputs (pode estar vazio, mas não None)"

        # Se houver variáveis obrigatórias sem default, o tftest levantará erro aqui.
        # Para módulos complexos, podemos injetar tfvars via tf.plan(tf_vars={...})

    except tftest.TerraformTestError as e:
        pytest.fail(f"Falha funcional no módulo {path_obj.name}: {e}")
