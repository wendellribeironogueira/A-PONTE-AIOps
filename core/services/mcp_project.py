#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

from fastmcp import FastMCP  # pyright: ignore [reportMissingImports]

from core.lib import toolbelt as tools  # noqa: E402
from core.lib import utils as common  # noqa: E402
from core.services import registry  # noqa: E402
from core.lib.mcp_utils import handle_mcp_errors

mcp = FastMCP("project")

@mcp.tool(name="normalize_name")
@handle_mcp_errors
def normalize_name(name: str, project_name: str = None, environment: str = None) -> str:
    """
    Normaliza um nome de projeto (slugify) aplicando as regras da plataforma.

    Examples:
        name='Meu Projeto Legal'
    """
    return common.normalize_project_name(name)


@mcp.tool(name="check_registry_availability")
@handle_mcp_errors
def check_registry_availability(project_name: str, environment: str = None) -> dict:
    """
    Valida se o Tenant ID já está registrado (DynamoDB + Local). Retorna JSON.

    Examples:
        project_name='ecommerce-prod'
    """
    # 1. Validação na Nuvem
    if registry.check_exists(project_name):
        return {
            "valid": False,
            "message": f"O projeto '{project_name}' já está registrado no DynamoDB.",
        }

    # 2. Validação Local
    root = common.get_project_root()
    project_dir = root / "projects" / project_name
    if project_dir.exists():
        return {
            "valid": False,
            "message": f"O projeto '{project_name}' já existe localmente.",
        }

    return {"valid": True, "message": ""}

if __name__ == "__main__":
    mcp.run()
