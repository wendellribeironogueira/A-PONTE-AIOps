#!/usr/bin/env python3
import os
import json
import re
import sys
from pathlib import Path
from fastmcp import FastMCP

from core.lib import utils as common
from core.lib import shell
from core.lib.mcp_utils import handle_mcp_errors, truncate_output

print("Iniciando FastMCP 'terraform'...")

mcp = FastMCP("terraform")

print("Mcp Terraform service started, version 2")


async def _run_terragrunt(args, project_name, **kwargs):
    """Executa Terragrunt diretamente, contornando o binário CLI (aponte)."""
    try:
        root = common.get_project_root()
        env = os.environ.copy()
        env["TF_VAR_project_name"] = project_name
        env["TF_IN_AUTOMATION"] = "true"
        env["TG_NON_INTERACTIVE"] = "true"
        
        if not project_name:
            return {"error": "Nome do projeto não fornecido e não pôde ser inferido."}

        for key, value in kwargs.items():
            if value:
                env[f"TF_VAR_{key}"] = value

        # Resolve diretório do projeto
        cwd = root / "projects" / project_name
        if project_name == "a-ponte":
             cwd = root / "infrastructure" / "bootstrap"
             
        if not cwd.exists():
             return {"error": f"Diretório do projeto não encontrado: {cwd}"}

        cmd = ["terragrunt"] + args
        
        result = await shell.run_command_async(cmd, cwd=str(cwd), env=env)

        if result["status"] == "success":
            return {"status": "success", "output": truncate_output(result["output"])}
        else:
            return {"status": "error", "output": truncate_output(result["output"])}

    except Exception as e:
        return {"error": str(e)}


@mcp.tool(name="tf_plan")
@handle_mcp_errors
async def tf_plan(
    project_name: str = None,
    environment: str = None,
    app_name: str = None,
    resource_name: str = None,
) -> dict:
    """
    Gera um plano de execução (Dry Run). Use para validar alterações de infraestrutura ou detectar drift antes de aplicar.

    Examples:
        project_name='ecommerce-prod'
    """
    result = await _run_terragrunt(
        ["plan", "-input=false"],
        project_name,
        environment=environment,
        app_name=app_name,
        resource_name=resource_name,
    )
    return result


@mcp.tool(name="tf_apply")
@handle_mcp_errors
async def tf_apply(
    authorization: str,
    project_name: str = None,
    environment: str = None,
    app_name: str = None,
    resource_name: str = None,
) -> dict:
    """
    Aplica mudanças de infraestrutura (Deploy). Use SOMENTE após confirmação explícita do usuário.

    Args:
        authorization: Deve ser 'AUTORIZADO' para prosseguir.

    Examples:
        authorization='AUTORIZADO'
    """
    if authorization.strip().upper() != "AUTORIZADO":
        return {
            "error": "Ação Bloqueada: Deploy requer autorização explícita ('AUTORIZADO')."
        }

    result = await _run_terragrunt(
        ["apply", "-auto-approve", "-input=false"],
        project_name,
        environment=environment,
        app_name=app_name,
        resource_name=resource_name,
    )
    return result


@mcp.tool(name="tf_rollback")
@handle_mcp_errors
async def tf_rollback(
    confirmation: str,
    project_name: str = None,
    environment: str = None,
    app_name: str = None,
    resource_name: str = None,
) -> dict:
    """
    Executa Rollback (Destroy). Use em emergências para reverter um deploy quebrado.

    Args:
        confirmation: Deve ser 'ROLLBACK_CONFIRMED'.

    Examples:
        confirmation='ROLLBACK_CONFIRMED'
    """
    if confirmation.strip().upper() != "ROLLBACK_CONFIRMED":
        return {
            "error": "Ação Bloqueada: Rollback requer confirmação explícita ('ROLLBACK_CONFIRMED')."
        }

    # Rollback mapeado para destroy neste contexto
    result = await _run_terragrunt(
        ["destroy", "-auto-approve", "-input=false"],
        project_name,
        environment=environment,
        app_name=app_name,
        resource_name=resource_name,
    )
    return result


@mcp.tool(name="tf_output")
@handle_mcp_errors
async def tf_output(project_name: str = None) -> dict:
    """
    Retorna outputs do Terraform. Use para obter IPs, URLs ou ARNs de recursos já provisionados.

    Examples:
        project_name='ecommerce-prod'
    """
    result = await _run_terragrunt(["output", "-json"], project_name)

    if result["status"] == "success":
        output_str = result["output"]
        try:
            return json.loads(output_str)
        except json.JSONDecodeError:
            # Fallback: Tenta encontrar JSON dentro de logs/texto (ex: banners da CLI)
            match = re.search(r"\{.*\}", output_str, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except:
                    pass
            return {"error": "Output inválido (Não é JSON)", "raw_output": output_str}
    else:
        return result


if __name__ == "__main__":
    mcp.run()
