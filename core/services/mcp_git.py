#!/usr/bin/env python3
import os
import urllib.parse
import shutil
from fastmcp import FastMCP

from core.lib import utils as common
from core.lib import shell
from core.lib.mcp_utils import handle_mcp_errors, truncate_output

# Inicializa o servidor FastMCP
mcp = FastMCP("git")


def validate_path(path: str, context_project: str = None) -> bool:
    """
    Valida se o caminho está dentro do escopo permitido do projeto.
    Previne Path Traversal e operações fora do diretório do projeto.
    """
    try:
        abs_path = Path(path).resolve()
        root = common.get_project_root().resolve() # Âncora estável

        # 1. Validação Básica: Deve estar dentro da raiz do A-PONTE
        if not str(abs_path).startswith(str(root)):
            return False

        # 2. Validação de Contexto (Isolamento de Tenant)
        if context_project and context_project not in ["home", "a-ponte"]:
            # Se um projeto específico for informado, o caminho DEVE estar dentro dele
            project_root = root / "projects" / context_project
            if not str(abs_path).startswith(str(project_root)):
                return False

        return True
    except Exception as e:
        sys.stderr.write(f"Erro na validação de caminho: {e}\n")
        return False


async def run_command(cmd, cwd=None):
    # Wrapper de compatibilidade para usar a nova lib centralizada
    res = await shell.run_command_async(cmd, cwd=cwd)
    if res["status"] == "success":
        return {"status": "success", "output": truncate_output(res["stdout"])} # Git tools esperam stdout limpo no sucesso
    return {"status": "error", "output": res["stderr"] or res["stdout"]} # E stderr no erro

async def _get_authenticated_url(repo_path, original_remote="origin"):
    """Gera URL autenticada com token para operações Git."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        return original_remote

    try:
        res = await shell.run_command_async(["git", "remote", "get-url", original_remote], cwd=repo_path)
        if res["returncode"] != 0:
            return original_remote
        remote_url = res["stdout"]

        if "github.com" in remote_url and "x-access-token" not in remote_url:
            if "******" in remote_url or remote_url.startswith("https://"):
                encoded_token = urllib.parse.quote(token, safe="")
                if "@" not in remote_url.split("://")[-1].split("/")[0]:
                    return remote_url.replace("https://", f"https://x-access-token:{encoded_token}@", 1)
    except Exception as e:
        sys.stderr.write(f"Warning: Falha ao gerar URL autenticada: {e}\n")
        pass
    return original_remote

@mcp.tool(name="git_clone")
@handle_mcp_errors
async def git_clone(
    repo_url: str, destination: str, project_name: str = None
) -> dict:
    """
    Clona um repositório. Use para baixar código de um projeto novo ou existente.

    Examples:
        repo_url='https://github.com/org/repo.git' destination='projects/my-app/repos/backend'
    """
    # Aceita project_name para compatibilidade com injeção do Architect, mas clone pode ser novo dir.
    if os.path.exists(destination):
        if not os.path.isdir(destination):
            return {"error": f"O destino existe e não é um diretório: {destination}"}
        if os.listdir(destination):
            return {"error": f"Diretório não está vazio: {destination}"}

    if not validate_path(destination, project_name):
        return {
            "error": f"Acesso negado: O destino '{destination}' está fora do escopo do projeto '{project_name}'."
        }

    result = await run_command(["git", "clone", repo_url, destination])

    # Fallback: Se falhar e for SSH, tenta HTTPS com token se disponível
    # Útil para ambientes Docker sem chaves SSH configuradas
    if result.get("status") == "error" and repo_url.startswith("git@"):
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            # Converte git@github.com:user/repo.git -> https://github.com/user/repo.git
            https_url = repo_url.replace(":", "/").replace("git@", "https://")
            if "github.com" in https_url:
                 encoded_token = urllib.parse.quote(token, safe="")
                 auth_url = https_url.replace("https://", f"https://x-access-token:{encoded_token}@", 1)

                 # Limpa diretório se foi criado parcialmente
                 if os.path.exists(destination):
                     shutil.rmtree(destination, ignore_errors=True)
                     # Verifica se a limpeza funcionou
                     if os.path.exists(destination):
                         # Se ainda existe, tenta renomear para lixo (Windows lock workaround)
                         trash = f"{destination}.trash.{os.getpid()}"
                         os.rename(destination, trash)

                 result = await run_command(["git", "clone", auth_url, destination])

                 # SECURITY FIX: Remove token do .git/config imediatamente após o clone
                 if result.get("status") == "success":
                     await run_command(["git", "remote", "set-url", "origin", https_url], cwd=destination)

                 return result

    return result


@mcp.tool(name="git_commit_push")
@handle_mcp_errors
async def git_commit_push(
    repo_path: str,
    message: str,
    branch: str = "main",
    project_name: str = None,
) -> dict:
    """
    Salva e envia mudanças. Use para persistir o trabalho realizado no repositório remoto.

    Examples:
        repo_path='projects/my-app/repos/backend' message='feat: add s3 bucket'
    """
    if not os.path.exists(repo_path):
        return {"error": f"Caminho não encontrado: {repo_path}"}

    if not validate_path(repo_path, project_name):
        return {
            "error": f"Acesso negado: O caminho '{repo_path}' está fora do escopo do projeto '{project_name}'."
        }

    # Add
    r1 = await run_command(["git", "add", "."], cwd=repo_path)
    if r1.get("status") == "error":
        return {"error": "Falha no git add", "details": r1}

    # Commit (pode falhar se nada mudou, não é erro fatal)
    r2 = await run_command(["git", "commit", "-m", message], cwd=repo_path)

    # Sync (Pull --rebase) para evitar rejeição
    # Tenta configurar upstream se necessário e puxar mudanças
    pull_cmd = ["git", "pull", "--rebase", "origin", branch]
    push_cmd = ["git", "push", "origin", branch]

    auth_url = await _get_authenticated_url(repo_path)
    if auth_url != "origin":
        pull_cmd = ["git", "pull", "--rebase", auth_url, branch]
        push_cmd = ["git", "push", auth_url, branch]

    # Executa Pull e depois Push
    r_pull = await run_command(pull_cmd, cwd=repo_path)

    # Short-circuit: Se o pull falhar (conflito), não tenta o push
    if r_pull.get("status") == "error":
        # FIX: Aborta o rebase para limpar o estado do repositório e evitar travamento
        await run_command(["git", "rebase", "--abort"], cwd=repo_path)
        return {"add": r1, "commit": r2, "pull_rebase": r_pull, "push": {"status": "skipped", "reason": "Pull failed (Rebase aborted)"}}

    r3 = await run_command(push_cmd, cwd=repo_path)

    return {"add": r1, "commit": r2, "pull_rebase": r_pull, "push": r3}


@mcp.tool(name="git_status")
@handle_mcp_errors
async def git_status(repo_path: str, project_name: str = None) -> dict:
    """
    Verifica status do repositório. Use para ver arquivos modificados antes de commitar.

    Args:
        repo_path: Caminho do repositório local.

    Examples:
        repo_path='projects/my-app/repos/backend'
    """
    if not os.path.exists(repo_path):
        return {"error": f"Caminho não encontrado: {repo_path}"}

    if not validate_path(repo_path, project_name):
        return {
            "error": f"Acesso negado: O caminho '{repo_path}' está fora do escopo do projeto '{project_name}'."
        }

    return await run_command(["git", "status"], cwd=repo_path)


@mcp.tool(name="git_log")
@handle_mcp_errors
async def git_log(
    repo_path: str, query: str = None, max_count: int = 5, project_name: str = None
) -> dict:
    """
    Retorna histórico de commits. Use para entender o que foi feito recentemente no código.

    Args:
        max_count: Limite de commits (Default: 5).

    Examples:
        query='fix' max_count=10
    """
    if not os.path.exists(repo_path):
        return {"error": f"Caminho não encontrado: {repo_path}"}
    if not validate_path(repo_path, project_name):
        return {"error": f"Acesso negado."}
    
    cmd = ["git", "log", f"-n {max_count}", "--oneline"]
    if query:
        cmd.extend(["--grep", query, "-i"])
    return await run_command(cmd, cwd=repo_path)


@mcp.tool(name="git_checkout")
@handle_mcp_errors
async def git_checkout(
    repo_path: str, target: str, project_name: str = None
) -> dict:
    """
    Alterna branches ou versões. Use para mudar de contexto ou reverter para uma versão anterior.

    Examples:
        repo_path='projects/my-app/repos/backend' target='develop'
    """
    if not os.path.exists(repo_path):
        return {"error": f"Caminho não encontrado: {repo_path}"}
    if not validate_path(repo_path, project_name):
        return {"error": f"Acesso negado."}

    # Executa checkout
    return await run_command(["git", "checkout", target], cwd=repo_path)


@mcp.tool(name="git_pull")
@handle_mcp_errors
async def git_pull(repo_path: str, project_name: str = None) -> dict:
    """
    Atualiza o repositório local. Use para sincronizar com o trabalho de outros membros da equipe.

    Examples:
        repo_path='projects/my-app/repos/backend'
    """
    if not os.path.exists(repo_path):
        return {"error": f"Caminho não encontrado: {repo_path}"}
    if not validate_path(repo_path, project_name):
        return {"error": f"Acesso negado."}

    cmd = ["git", "pull"]
    auth_url = await _get_authenticated_url(repo_path)
    if auth_url != "origin":
        cmd.append(auth_url)

    result = await run_command(cmd, cwd=repo_path)

    if result.get("status") == "error":
        # Auto-Cleanup: Tenta abortar merge ou rebase pendente para não travar o repo
        await run_command(["git", "merge", "--abort"], cwd=repo_path)
        await run_command(["git", "rebase", "--abort"], cwd=repo_path)
        result["output"] += "\n(Note: Merge/Rebase aborted automatically to restore clean state)"

    return result


if __name__ == "__main__":
    mcp.run()
