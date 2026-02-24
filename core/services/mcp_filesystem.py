#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from fastmcp import FastMCP

from core.lib import utils as common
from core.services import versioning
from core.lib.mcp_utils import handle_mcp_errors

# Inicializa o servidor FastMCP
mcp = FastMCP("filesystem")

def validate_path(path: str, context_project: str = None) -> bool:
    """
    Valida se o caminho está dentro do escopo permitido (Security Sandbox).
    Impede Path Traversal e acesso fora da raiz do projeto.
    """
    try:
        root = common.get_project_root().resolve()
        abs_path = (root / path).resolve()

        # Deve estar dentro da raiz do A-PONTE
        if not str(abs_path).startswith(str(root)):
            return False

        # Proteção de arquivos sensíveis do sistema
        if abs_path.name.startswith(".env") or ".git" in str(abs_path):
            return False

        return True
    except Exception as e:
        sys.stderr.write(f"Erro na validação de caminho: {e}\n")
        return False

@mcp.tool(name="read_file")
@handle_mcp_errors
def read_file(path: str, project_name: str = None, environment: str = None) -> dict:
    """
    Lê o conteúdo de um arquivo. Use para entender o código existente.

    Examples:
        path='infrastructure/main.tf'
    """
    if not validate_path(path, project_name):
        return {"error": f"Acesso negado ou caminho inválido: {path}"}

    target = common.get_project_root() / path
    if not target.exists():
        return {"error": f"Arquivo não encontrado: {path}"}

    if not target.is_file():
        return {"error": f"O caminho não é um arquivo: {path}"}

    content = target.read_text(encoding="utf-8")
    return {"content": content, "path": str(target)}

@mcp.tool(name="save_file")
@handle_mcp_errors
def save_file(path: str, content: str, project_name: str = None, environment: str = None) -> dict:
    """
    Salva conteúdo em um arquivo.
    CRÍTICO: Aciona automaticamente o versionamento (ADR-018) antes de sobrescrever.

    Examples:
        path='infrastructure/variables.tf' content='variable "region" { default = "us-east-1" }'
    """
    if not validate_path(path, project_name):
        return {"error": f"Acesso negado ou caminho inválido: {path}"}

    target = common.get_project_root() / path

    # Cria diretórios pai se não existirem
    target.parent.mkdir(parents=True, exist_ok=True)

    # Safety Net: Versionamento automático se o arquivo já existir
    backup_id = None
    if target.exists():
        try:
            # Usa o nome do projeto do contexto ou 'home' se não definido
            p_name = project_name or common.read_context() or "home"
            backup_id = versioning.version_generic_file(target, p_name, reason="Pre-Save Backup (AI)")
        except Exception as e:
            return {"error": f"Falha ao criar backup de segurança. Operação abortada: {str(e)}"}

    target.write_text(content, encoding="utf-8")
    return {"status": "success", "path": str(target), "backup_id": backup_id}

@mcp.tool(name="list_directory")
@handle_mcp_errors
def list_directory(path: str = ".", query: str = None, limit: int = 50, project_name: str = None, environment: str = None) -> dict:
    """
    Lista arquivos e pastas em um diretório.

    Args:
        limit: Máximo de itens a retornar (Default: 50).

    Examples:
        path='src' limit=20
    """
    if not validate_path(path, project_name):
        return {"error": f"Acesso negado: {path}"}

    target = common.get_project_root() / path
    if not target.exists() or not target.is_dir():
        return {"error": f"Diretório não encontrado: {path}"}

    items = []
    for item in target.iterdir():
        if item.name.startswith("."): continue # Ignora ocultos
        kind = "DIR" if item.is_dir() else "FILE"
        items.append(f"[{kind}] {item.name}")

    if query:
        items = [i for i in items if query.lower() in i.lower()]

    total = len(items)
    truncated = False
    if total > limit:
        items = sorted(items)[:limit]
        truncated = True
    else:
        items = sorted(items)

    result = {"items": items, "path": str(target), "total_found": total}
    if truncated:
        result["warning"] = f"Output truncated ({limit}/{total} items). Use query to filter."
    return result

if __name__ == "__main__":
    mcp.run()