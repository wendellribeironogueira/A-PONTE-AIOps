import os
import sys
from pathlib import Path
from typing import Dict, Optional

from core.lib import utils as common

ROOT_DIR = common.get_project_root()
PROJECTS_DIR = ROOT_DIR / "projects"


def read_project_config(project: str) -> Optional[Dict]:
    """Lê e parseia o arquivo de configuração .project.yml."""
    config_file = PROJECTS_DIR / f"{project}.project.yml"
    if not config_file.exists():
        common.log_warning(f"AVISO: Cache local {config_file} não encontrado.")
        common.log_info("🔄 Tentando recuperar configuração do DynamoDB (ADR-008)...")

        config = _fetch_from_dynamodb(project)
        if config:
            _save_to_cache(project, config)
            return config

        common.log_error("❌ ERRO CRÍTICO: Configuração do projeto não encontrada (Local ou Remota).")
        return None

    try:
        # O formato original era `key=value`. Este parser é compatível.
        config = {}
        with open(config_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Suporte híbrido: YAML (key: value) e Legacy (key=value)
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                elif ":" in line:
                    key, value = line.strip().split(":", 1)
                else:
                    continue

                config[key.strip()] = value.strip().strip('"').strip("'")
        return config
    except Exception as e:
        common.log_error(f"Erro ao ler o arquivo de configuração: {e}")
        return None


def _fetch_from_dynamodb(project_name: str) -> Optional[Dict]:
    """Busca metadados do projeto no DynamoDB (Single Source of Truth)."""
    try:
        import boto3
        # Assume que as credenciais AWS estão configuradas no ambiente
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("a-ponte-registry")
        response = table.get_item(Key={"ProjectName": project_name})

        if "Item" in response:
            item = response["Item"]
            # Converte tipos do DynamoDB para string config
            return {
                "is_production": str(item.get("IsProduction", False)).lower(),
                "environment": item.get("Environment", "dev"),
                "app_name": item.get("AppName", project_name)
            }
    except ImportError:
        common.log_warning("⚠️  boto3 não instalado. Impossível conectar ao DynamoDB.")
    except Exception as e:
        common.log_warning(f"⚠️  Falha ao conectar ao DynamoDB: {e}")

    return None


def _save_to_cache(project: str, config: Dict):
    """Salva a configuração recuperada no arquivo local (Cache)."""
    try:
        config_file = PROJECTS_DIR / f"{project}.project.yml"
        with open(config_file, "w") as f:
            for k, v in config.items():
                f.write(f"{k}: {v}\n")
        common.log_info(f"✅ Cache local restaurado em: {config_file}")
    except Exception as e:
        common.log_error(f"Falha ao salvar cache local: {e}")


def is_production_project(project: str) -> bool:
    """Verifica se o projeto está marcado como produção."""
    config = read_project_config(project)
    if not config:
        return True  # Fail-safe: se não há config, assume que é produção para bloquear.

    is_prod = config.get("is_production", "false").lower()
    return is_prod == "true"


def guardrail_block_home_context(project: str, operation: str) -> bool:
    """Bloqueia operações perigosas no contexto 'home'."""
    if project != "home":
        return True  # Não bloqueia

    safe_operations = {"list", "navigate", "read", "switch", "create", "detect", "info"}
    if operation in safe_operations:
        return True

    common.log_error("Ação bloqueada em 'home' (contexto neutro)")
    common.log_info("   Selecione um projeto primeiro: aponte project switch <nome>")
    return False


def guardrail_block_aponte_context(project: str) -> bool:
    """Aplica guardrails para o projeto core 'a-ponte'."""
    if project != "a-ponte":
        return True

    if os.getenv("DENY_APONTE_MODIFICATIONS", "false").lower() == "true":
        common.log_error(
            "A-ponte bloqueado explicitamente via DENY_APONTE_MODIFICATIONS=true"
        )
        return False

    if os.getenv("ALLOW_APONTE_MODIFICATIONS", "false").lower() != "true":
        common.log_error("Modificações no projeto CORE 'a-ponte' estão bloqueadas.")
        common.log_info(
            "   Para desbloquear (perigoso): export ALLOW_APONTE_MODIFICATIONS=true"
        )
        return False

    common.log_warning("AVISO: Você está modificando o projeto CORE 'a-ponte'!")
    return True


def guardrail_check_destroy_permission(project: str) -> bool:
    """Função central que valida todas as permissões para uma operação de destroy."""
    if not guardrail_block_home_context(
        project, "destroy"
    ) or not guardrail_block_aponte_context(project):
        return False

    if is_production_project(project):
        if os.getenv("ALLOW_PRODUCTION_DESTROY", "false").lower() != "true":
            common.log_error(f"Destroy bloqueado: '{project}' é um projeto de PRODUÇÃO")
            common.log_info(
                "   Para forçar (perigoso): export ALLOW_PRODUCTION_DESTROY=true"
            )
            return False
        else:
            common.log_warning(
                "🔥 AVISO: Destruindo projeto de PRODUÇÃO (Flag de override ativa)"
            )

    return True


def confirm_destructive_operation(operation_msg: str, project: str) -> bool:
    """Exige confirmação interativa para operações destrutivas."""
    if (
        not sys.stdout.isatty()
        and os.getenv("FORCE_NON_INTERACTIVE", "false").lower() != "true"
    ):
        common.log_error("Operação destrutiva requer terminal interativo (TTY).")
        return False

    common.console.print(
        f"\n[bold red]⚠️  ATENÇÃO: Operação Destrutiva[/bold red]\n   Ação: {operation_msg}\n   Projeto: {project}\n"
    )
    confirm_input = common.console.input(
        f"   Digite o nome do projeto ('{project}') para confirmar: "
    )
    if confirm_input != project:
        common.log_error(
            f"Confirmação falhou. Esperado: '{project}', Recebido: '{confirm_input}'"
        )
        return False
    return True
