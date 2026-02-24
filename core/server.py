#!/usr/bin/env python3
"""
A-PONTE Core MCP Server
-----------------------
Servidor unificado que expõe as capacidades da plataforma via Model Context Protocol.
Este servidor agrega ferramentas de operação, diagnóstico e gestão de projetos.

Uso:
    python3 core/server.py
"""

import json
import os
import subprocess  # nosec B404 - Used to delegate to trusted local Go binary (SSOT)
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path
project_root = Path(__file__).parents[1].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common  # noqa: E402

try:
    from fastmcp import FastMCP
except ImportError:
    sys.exit("❌ Erro: fastmcp não instalado. Execute: pip install fastmcp")

try:
    import requests
except ImportError:
    sys.exit("❌ Erro: requests não instalado. Execute: pip install requests")

try:
    import docker
    from docker.errors import DockerException
except ImportError:
    docker = None
    DockerException = None

# Inicializa o Servidor FastMCP
mcp = FastMCP(
    "A-PONTE Core",
)

# --- Ferramentas de Sistema ---


@mcp.tool()
def get_platform_status() -> str:
    """Retorna o status atual da plataforma e contexto ativo."""
    # OTIMIZAÇÃO: Leitura direta via biblioteca (Remove overhead de subprocesso)
    context = common.read_context()

    aws_v, tf_v = common.get_tool_versions()
    return f"""
    ✅ A-PONTE Platform Online
    --------------------------
    Contexto Ativo: {context}
    AWS CLI: {aws_v}
    Terraform: {tf_v}
    Raiz: {common.get_project_root()}
    """


@mcp.tool()
def list_projects() -> str:
    """Lista os projetos registrados na plataforma."""
    # Delega para a CLI Go (Binário Local) para garantir consistência
    root = common.get_project_root()
    bin_path = root / "bin" / "aponte"
    cmd = (
        [str(bin_path), "project", "list"]
        if bin_path.exists()
        else ["aponte", "project", "list"]
    )

    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True
        )  # nosec B603 - Trusted local binary with fixed args
        return res.stdout
    except Exception as e:
        return f"Erro ao listar projetos: {e}"


@mcp.tool()
def check_health() -> str:
    """Realiza um healthcheck completo dos componentes da plataforma (Ollama, Docker, CLI)."""
    status = {
        "cli": "UNKNOWN",
        "ollama": "UNKNOWN",
        "docker": "UNKNOWN",
        "mcp_terraform": "UNKNOWN",
        "mcp_server": "ONLINE",
    }

    # 1. Check CLI (SSOT)
    root = common.get_project_root()
    bin_path = root / "bin" / "aponte"
    if not (bin_path.exists() and os.access(str(bin_path), os.X_OK)):
        status["cli"] = "❌ MISSING (Run 'go build -o bin/aponte cli/main.go')"
    else:
        status["cli"] = "✅ ONLINE (Binary Found & Executable)"

    # 2. Check Ollama (Docker)
    ollama_host = os.getenv("OLLAMA_HOST", "localhost")
    ollama_port = os.getenv("OLLAMA_PORT", "11434")
    ollama_url = f"http://{ollama_host}:{ollama_port}"

    try:
        # Tenta conectar na API de tags do Ollama usando a biblioteca requests
        response = requests.get(f"{ollama_url}/api/tags", timeout=2)
        response.raise_for_status()  # Lança exceção para códigos de erro HTTP (4xx ou 5xx)
        data = response.json()
        models = [m.get("name") for m in data.get("models", [])]
        status["ollama"] = f"✅ ONLINE (Models: {len(models)})"
    except requests.exceptions.RequestException:
        status["ollama"] = "❌ UNREACHABLE (Is Docker Up?)"
    except json.JSONDecodeError:
        status["ollama"] = "⚠️ UNSTABLE (Invalid Response)"

    # 3. Check Docker
    if docker and DockerException:
        try:
            client = docker.from_env(timeout=2)
            client.ping()
            status["docker"] = "✅ ONLINE"

            # 4. Check MCP Terraform Container (Sandbox)
            try:
                container = client.containers.get("mcp-terraform")
                if container.status == "running":
                    status["mcp_terraform"] = "✅ ONLINE"
                else:
                    status["mcp_terraform"] = f"❌ STOPPED ({container.status})"
            except docker.errors.NotFound:
                status["mcp_terraform"] = "❌ MISSING (Run 'aponte infra up')"
            except Exception:
                status["mcp_terraform"] = "⚠️ ERROR"
        except DockerException:
            status["docker"] = "❌ ERROR (Daemon down or No Perms)"
            status["mcp_terraform"] = "❌ UNREACHABLE"
    else:
        status["docker"] = "⚠️ NOT CHECKED (Run 'pip install docker')"
        status["mcp_terraform"] = "⚠️ SKIPPED"

    return f"""
    🏥 A-PONTE Healthcheck
    ----------------------
    🔌 MCP Server: {status['mcp_server']}
    🐚 CLI (Go):   {status['cli']}
    🐳 Docker:     {status['docker']}
    🏗️  Sandbox:    {status['mcp_terraform']}
    🧠 Ollama:     {status['ollama']}
    """


@mcp.resource("aponte://core/state")
def get_state() -> str:
    """Retorna o estado atual do contexto (Projeto, Ambiente, Região)."""
    project = common.read_context()
    env = os.getenv("TF_VAR_environment", "dev")
    return json.dumps({
        "project_name": project,
        "environment": env,
        "aws_region": os.getenv("AWS_REGION", "sa-east-1"),
        "account_id": os.getenv("TF_VAR_account_id", "unknown")
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
