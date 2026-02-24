#!/usr/bin/env python3
import subprocess
import sys
import shutil

# Tenta importar rich para output bonito, com fallback gracioso
try:
    from rich.console import Console
    from rich.panel import Panel
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

def log(msg, style=None):
    if HAS_RICH and style:
        console.print(f"[{style}]{msg}[/]")
    else:
        print(msg)

def run_in_mcp(command):
    """Executa comando dentro do container MCP para validar o ambiente interno."""
    if not shutil.which("docker"):
        return False, "", "Docker não encontrado no PATH"

    # Suporte a lista de argumentos para comandos complexos (ex: python -c "...")
    if isinstance(command, list):
        cmd_args = command
    else:
        cmd_args = command.split()

    # Usa o nome do container definido no docker-compose.yml
    docker_cmd = ["docker", "exec", "mcp-terraform"] + cmd_args
    try:
        result = subprocess.run(docker_cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def validate_mcp():
    if HAS_RICH:
        console.rule("[bold blue]🏭 Validação da Fábrica MCP (Terraform Sandbox)[/]")
    else:
        print("--- Validação da Fábrica MCP (Terraform Sandbox) ---")

    # Lista de ferramentas críticas que DEVEM existir na fábrica
    checks = [
        ("Terraform", ["terraform", "--version"]),
        ("Terragrunt", ["terragrunt", "--version"]),
        ("TFLint", ["tflint", "--version"]),
        ("Checkov", ["checkov", "--version"]),
        ("Trivy", ["trivy", "--version"]),
        ("Prowler", ["prowler", "--version"]),
        ("Gitleaks", ["gitleaks", "version"]),
        ("Bandit", ["bandit", "--version"]),
        ("Python (Internal)", ["python3", "--version"]),
        ("FastMCP Lib", ["python3", "-c", "import fastmcp; print(fastmcp.__version__)"]),
    ]

    all_pass = True

    # 1. Check Tools (Toolchain)
    log("1. Verificando Toolchain (Versões):", "bold")
    for name, cmd in checks:
        ok, out, err = run_in_mcp(cmd)
        if ok:
            # Pega apenas a primeira linha da versão para não poluir
            version = out.split('\n')[0] if out else "OK"
            log(f"  ✅ {name}: {version}", "green")
        else:
            log(f"  ❌ {name}: Falha na execução ({err})", "red")
            all_pass = False

    # 2. Check Mounts (Filesystem)
    log("\n2. Verificando Montagem de Volumes (Contexto do Projeto):", "bold")
    # Verifica se o diretório /app tem conteúdo (o projeto montado)
    ok, out, err = run_in_mcp("ls /app/Makefile")
    if ok:
        log("  ✅ Project Root (/app): Acessível e Populado", "green")
    else:
        log(f"  ❌ Project Root (/app): Vazio ou Inacessível. Makefile não encontrado. ({err})", "red")
        # Debug: Tenta listar o diretório para entender o que está lá
        _, debug_out, _ = run_in_mcp("ls -A /app")
        log(f"  ❌ Project Root (/app): Vazio ou Inacessível. Conteúdo de /app: '{debug_out}'. Erro: ({err})", "red")
        all_pass = False

    # 3. Check Network/DNS
    log("\n3. Verificando Conectividade (Internet):", "bold")
    ok, out, err = run_in_mcp("curl -I https://github.com --max-time 5")
    if ok:
        log("  ✅ Internet (GitHub): Acessível", "green")
    else:
        log(f"  ⚠️  Internet: Falha ({err}) - Pode afetar 'terraform init' se precisar baixar providers.", "yellow")

    # 4. Check AWS Credentials (Optional/Contextual)
    log("\n4. Verificando Credenciais AWS (ReadOnly):", "bold")
    # Adaptação para Boto3 (AWS CLI removido do container para otimização)
    cmd = ["python3", "-c", "import boto3; print(boto3.client('sts').get_caller_identity()['Account'])"]
    ok, out, err = run_in_mcp(cmd)
    if ok:
        log("  ✅ AWS Identity: Configurado e Válido", "green")
    else:
        log("  ⚠️  AWS Identity: Não detectado (Esperado se não houver credenciais no host ou profile inválido)", "yellow")

    if all_pass:
        msg = "A Fábrica MCP está Operacional e Validada!"
        if HAS_RICH:
            console.print(Panel(f"[bold green]{msg}[/]", border_style="green"))
        sys.exit(0)
    else:
        msg = "Falha Crítica na validação do MCP! A fábrica não está pronta."
        if HAS_RICH:
            console.print(Panel(f"[bold red]{msg}[/]", border_style="red"))
        sys.exit(1)

if __name__ == "__main__":
    validate_mcp()
