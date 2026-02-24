#!/usr/bin/env python3
from fastmcp import FastMCP
import os
from pathlib import Path

# Define a raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parents[2]

from core.lib import utils as common
from core.lib import shell
from core.lib.mcp_utils import handle_mcp_errors, truncate_output

mcp = FastMCP("mcp-ops")

async def run_cli(args, project_name=None, environment=None):
    env = {}
    if project_name:
        env["TF_VAR_project_name"] = project_name

    cmd = ["aponte"] + args

    cmd[0] = common.resolve_local_binary(cmd[0])

    res = await shell.run_command_async(cmd, cwd=str(PROJECT_ROOT), env=env)
    return truncate_output(res["output"])

@mcp.tool(name="diagnose_system")
@handle_mcp_errors
async def diagnose_system(project_name: str = None, environment: str = None) -> str:
    """
    Executa diagnóstico do sistema. Use quando houver erros desconhecidos ou falhas operacionais.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: O diagnóstico requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."
    return await run_cli(["doctor"], project_name)

@mcp.tool(name="train_knowledge_base")
@handle_mcp_errors
async def train_knowledge_base(project_name: str = None, environment: str = None) -> str:
    """
    Treina a base de conhecimento da IA. Use após adicionar novos documentos ou ADRs para atualizar o cérebro.
    """
    return await run_cli(["ai", "train"], project_name)

@mcp.tool(name="ingest_sources")
@handle_mcp_errors
async def ingest_sources(project_name: str = None, environment: str = None) -> str:
    """
    Ingere novas fontes de conhecimento. Use para processar URLs ou arquivos adicionados à lista de aprendizado.
    """
    return await run_cli(["ai", "ingest"], project_name)

@mcp.tool(name="detect_drift")
@handle_mcp_errors
async def detect_drift(project_name: str = None, environment: str = None) -> str:
    """
    Detecta alterações manuais. Use para verificar se a infraestrutura real difere do código.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A detecção de drift requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."
    return await run_cli(["drift"], project_name)

@mcp.tool(name="estimate_cost")
@handle_mcp_errors
async def estimate_cost(project_name: str = None, environment: str = None) -> str:
    """
    Gera estimativa de custos. Use para prever o impacto financeiro das mudanças de infraestrutura.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A estimativa de custos requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."
    return await run_cli(["cost"], project_name)

@mcp.tool(name="run_security_audit")
@handle_mcp_errors
async def run_security_audit(project_name: str = None, environment: str = None) -> str:
    """
    Executa auditoria de segurança. Use para identificar vulnerabilidades em código e infraestrutura.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A auditoria de segurança requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."
    return await run_cli(["security", "audit"], project_name)

@mcp.tool(name="run_pipeline")
@handle_mcp_errors
async def run_pipeline(project_name: str = None, environment: str = None) -> str:
    """
    Executa pipeline de validação. Use para rodar todos os testes e verificações de qualidade antes de um deploy.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A execução de pipeline requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."
    return await run_cli(["pipeline"], project_name)

@mcp.tool(name="checkov")
@handle_mcp_errors
async def checkov(project_name: str = None, environment: str = None) -> str:
    """
    Executa Checkov (IaC Security). Use para validar arquivos Terraform contra políticas de segurança.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A execução do Checkov requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."

    # FIX: Execução direta no container para garantir escopo correto (ADR-028)
    cmd = ["docker", "exec", "mcp-terraform", "checkov", "-d", f"/app/projects/{project_name}", "--compact", "--skip-path", ".terragrunt-cache", "--skip-path", ".git"]
    res = await shell.run_command_async(cmd)
    return truncate_output(res["output"])

@mcp.tool(name="tfsec")
@handle_mcp_errors
async def tfsec(project_name: str = None, environment: str = None) -> str:
    """
    Executa TFSec. Use para análise estática de segurança em Terraform.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A execução do TFSec requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."

    # FIX: Execução direta no container
    cmd = ["docker", "exec", "mcp-terraform", "tfsec", f"/app/projects/{project_name}", "--concise-output", "--exclude-path", ".terragrunt-cache,.git"]
    res = await shell.run_command_async(cmd)
    return truncate_output(res["output"])

@mcp.tool(name="tflint")
@handle_mcp_errors
async def tflint(project_name: str = None, environment: str = None) -> str:
    """
    Executa TFLint. Use para verificar boas práticas e erros em arquivos Terraform.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A execução do TFLint requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."

    # FIX: Execução direta no container (Aponta config global para garantir regras)
    cmd = ["docker", "exec", "mcp-terraform", "tflint", "--config", "/app/.tflint.hcl", "--chdir", f"/app/projects/{project_name}", "--format", "compact"]
    res = await shell.run_command_async(cmd)
    return truncate_output(res["output"])

@mcp.tool(name="trivy")
@handle_mcp_errors
async def trivy(project_name: str = None, environment: str = None) -> str:
    """
    Executa Trivy. Use para escanear vulnerabilidades em containers e sistema de arquivos.

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A execução do Trivy requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."

    # FIX: Execução direta no container
    cmd = ["docker", "exec", "mcp-terraform", "trivy", "fs", f"/app/projects/{project_name}", "--scanners", "vuln,secret,config", "--skip-dirs", ".terragrunt-cache", "--skip-dirs", ".git"]
    res = await shell.run_command_async(cmd)
    return truncate_output(res["output"])

@mcp.tool(name="prowler")
@handle_mcp_errors
async def prowler(project_name: str = None, environment: str = None) -> str:
    """
    Executa Prowler. Use para auditoria de conformidade AWS (CIS, GDPR).

    Examples:
        project_name='ecommerce-prod'
    """
    if not project_name or project_name == "home":
        return "⛔ Erro: A execução do Prowler requer um contexto de projeto. Use 'aponte project use <nome>' ou passe o argumento 'project_name'."
    return await run_cli(["security", "prowler"], project_name)

@mcp.tool(name="clean_cache")
@handle_mcp_errors
async def clean_cache(project_name: str = None, environment: str = None) -> str:
    """
    Limpa caches temporários (Terragrunt, Terraform). Use quando houver erros de 'module not found' ou resultados de auditoria presos/antigos.
    """
    # Comando 1: Terragrunt Cache (Recursivo em /app)
    cmd_tg = ["docker", "exec", "mcp-terraform", "find", "/app", "-type", "d", "-name", ".terragrunt-cache", "-prune", "-exec", "rm", "-rf", "{}", "+"]
    await shell.run_command_async(cmd_tg)

    # Comando 2: Terraform Cache
    cmd_tf = ["docker", "exec", "mcp-terraform", "find", "/app", "-type", "d", "-name", ".terraform", "-prune", "-exec", "rm", "-rf", "{}", "+"]
    await shell.run_command_async(cmd_tf)

    return "✅ Cache de infraestrutura (Terragrunt/Terraform) limpo com sucesso. Próxima execução fará download limpo."

if __name__ == "__main__":
    mcp.run()