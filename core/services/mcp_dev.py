"""
MCP Development Service
-----------------------
Responsável pelas operações de "Mãos na Massa":
1. Gerar código (via Local Coder/Ollama).
2. Manipular arquivos (Salvar, Ler).
3. Validar sintaxe.
"""
import sys
import os
import re
from pathlib import Path
from fastmcp import FastMCP

from core.lib import utils as common
from core.lib import toolbelt as tools
from core.services import versioning
from core.lib.mcp_utils import handle_mcp_errors

# Importação segura para evitar crash do serviço se o módulo tools estiver quebrado
try:
    from core.tools import local_coder
except ImportError as e:
    local_coder = None
    IMPORT_ERROR = str(e)

mcp = FastMCP("A-PONTE Developer Tools")

def _get_draft_path():
    return common.get_project_root() / ".aponte-versions" / "tmp" / "last_generated_draft.txt"

def _build_context_block(project_name_override=None):
    """Reconstrói o contexto do projeto a partir do ambiente para o Coder."""
    project = project_name_override or os.getenv("TF_VAR_project_name") or common.read_context()
    if not project or project == "home":
        return "CONTEXTO: Projeto não definido."

    return f"""
CONTEXTO DO PROJETO:
- Project: {project}
- Env: {os.getenv("TF_VAR_environment", "dev")}
- App: {os.getenv("TF_VAR_app_name", "unknown")}
- Region: {os.getenv("AWS_REGION", "sa-east-1")}
"""

@mcp.tool(name="generate_code")
@handle_mcp_errors
def generate_code(instruction: str, filename: str = None, project_name: str = None, environment: str = None) -> str:
    """
    Gera ou modifica código (Terraform/Python). Use para criar infraestrutura ou scripts solicitados pelo usuário.

    Examples:
        instruction='Crie um bucket S3 com versionamento ativado' filename='s3.tf'
    """
    if not local_coder:
        return f"Erro Crítico: Módulo 'local_coder' não carregado. Detalhe: {globals().get('IMPORT_ERROR', 'Unknown')}"

    target_project = project_name or os.getenv("TF_VAR_project_name") or common.read_context()
    context = _build_context_block(target_project)

    # Resolve diretório
    root = common.get_project_root()
    project_dir = root / "projects" / target_project if target_project != "home" else root

    code = local_coder.generate_code(instruction, context, project_dir=project_dir, filename=filename)

    if code:
        try:
            draft_path = _get_draft_path()
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(code, encoding="utf-8")
            return f"CÓDIGO GERADO (Rascunho salvo em disco):\n\n{code}\n\nIMPORTANTE: O código acima NÃO foi salvo no projeto. Para persistir, use a ferramenta 'save_file'."
        except Exception as e:
            return f"Erro ao salvar rascunho: {e}"

    return "Erro: O Operário Local não retornou código válido."

@mcp.tool(name="save_file")
@handle_mcp_errors
def save_file(filename: str, content: str = None, project_name: str = None, environment: str = None) -> str:
    """
    Salva conteúdo em arquivo. Use para persistir o código gerado pelo 'generate_code'.

    Examples:
        filename='main.tf'
    """
    content_to_write = content

    if content_to_write is None:
        draft_path = _get_draft_path()
        if draft_path.exists():
            content_to_write = draft_path.read_text(encoding="utf-8")

    if not content_to_write:
        return "Erro: Nenhum conteúdo fornecido e nenhum rascunho encontrado em disco."

    target_project = project_name or os.getenv("TF_VAR_project_name") or common.read_context()
    root = common.get_project_root()

    if target_project == "a-ponte":
        target_dir = root / "infrastructure" / "bootstrap"
    elif target_project and target_project != "home":
        target_dir = root / "projects" / target_project
    else:
        return "Erro: Nenhum projeto selecionado para salvar o arquivo."

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = (target_dir / filename).resolve()

    # Security Check: Jail Enforcement (Garante que o arquivo final está dentro da raiz)
    if not str(target_file).startswith(str(root)):
        return f"Erro de Segurança: O caminho resultante '{target_file}' foge da raiz do projeto."

    # Validação de Sintaxe (Safety Net)
    if filename.endswith(".tf") and not tools.validate_hcl_syntax(content_to_write):
        return "Erro de Validação: O código HCL gerado é inválido. Corrija antes de salvar."

    # Versionamento (Backup)
    if target_file.exists():
        try:
            versioning.version_generic_file(target_file, target_project, reason="Pre-Save-Backup")
        except Exception as e:
            return f"Erro ao criar backup: {e}"

    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content_to_write, encoding="utf-8")
        return f"✅ Arquivo salvo com sucesso: {target_file.relative_to(root)}"
    except Exception as e:
        return f"Erro ao salvar arquivo: {e}"

@mcp.tool(name="read_file")
@handle_mcp_errors
def read_file(path: str, project_name: str = None, environment: str = None) -> str:
    """
    Lê um arquivo. Use para entender o contexto ou conteúdo atual antes de fazer alterações.

    Examples:
        path='infrastructure/main.tf'
    """
    # Security Check: Path Traversal
    if ".." in path or path.startswith("/"):
         return "Erro de Segurança: Caminho de arquivo inválido."

    root = common.get_project_root()
    target_file = (root / path).resolve()

    # Garante que o arquivo está dentro da raiz do projeto
    if not str(target_file).startswith(str(root)):
        return "Erro de Segurança: Acesso negado fora da raiz do projeto."

    if not target_file.exists():
        return f"Erro: Arquivo não encontrado: {path}"

    if not target_file.is_file():
        return f"Erro: O caminho não é um arquivo: {path}"

    try:
        return target_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Erro ao ler arquivo: {e}"

@mcp.tool(name="list_directory")
@handle_mcp_errors
def list_directory(path: str = ".", project_name: str = None, environment: str = None) -> str:
    """
    Lista arquivos em um diretório. Use para explorar a estrutura do projeto e encontrar arquivos.

    Examples:
        path='infrastructure'
    """
    root = common.get_project_root()
    target_dir = (root / path).resolve()

    if not str(target_dir).startswith(str(root)):
        return "Erro de Segurança: Acesso negado."

    if not target_dir.exists() or not target_dir.is_dir():
        return f"Erro: Diretório não encontrado: {path}"

    items = [f"{'📁' if p.is_dir() else '📄'} {p.name}" for p in sorted(target_dir.iterdir())]
    return "\n".join(items)

if __name__ == "__main__":
    mcp.run()