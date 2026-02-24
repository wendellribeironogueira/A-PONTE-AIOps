#!/usr/bin/env python3
import sys
import os
from pathlib import Path
from fastmcp import FastMCP
from core.lib.mcp_utils import handle_mcp_errors

# Define a raiz do projeto (assumindo que este script está em core/services/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Inicializa o servidor FastMCP
mcp = FastMCP("snippets")

def _get_snippets_dir():
    snippets_dir = PROJECT_ROOT / "templates" / "snippets"
    # Garante que o diretório existe para evitar erros
    snippets_dir.mkdir(parents=True, exist_ok=True)
    return snippets_dir

@mcp.tool(name="list_snippets")
@handle_mcp_errors
def list_snippets(project_name: str = None, environment: str = None) -> dict:
    """
    Lista os snippets de infraestrutura (Terraform) disponíveis na biblioteca local.

    Examples:
        (Sem argumentos)
    """
    snippets_dir = _get_snippets_dir()
    # Lista arquivos .tf
    files = [f.name for f in snippets_dir.glob("*.tf")]
    return {"snippets": files, "count": len(files)}

@mcp.tool(name="get_snippet")
@handle_mcp_errors
def get_snippet(filename: str, project_name: str = None, environment: str = None) -> dict:
    """
    Lê o conteúdo de um snippet de infraestrutura.

    Args:
        filename: Nome do arquivo (ex: 's3_secure.tf') obtido via list_snippets.

    Examples:
        filename='s3_secure.tf'
    """
    snippets_dir = _get_snippets_dir()
    target_file = snippets_dir / filename

    # Segurança: Validação de Path Traversal
    try:
        # Resolve links simbólicos e caminhos absolutos
        target_abs = target_file.resolve()
        snippets_abs = snippets_dir.resolve()

        # Verifica se o arquivo alvo está dentro do diretório de snippets
        # (Compatível com Python < 3.9 que não tem is_relative_to)
        if not str(target_abs).startswith(str(snippets_abs)):
             return {"error": "Acesso negado: Tentativa de path traversal."}
    except Exception as e:
        return {"error": f"Erro ao validar caminho: {str(e)}"}

    if not target_file.exists():
        return {"error": f"Snippet '{filename}' não encontrado."}

    try:
        content = target_file.read_text(encoding="utf-8")
        return {"filename": filename, "content": content}
    except Exception as e:
        return {"error": f"Erro ao ler arquivo: {str(e)}"}

if __name__ == "__main__":
    mcp.run()
