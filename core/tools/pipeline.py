#!/usr/bin/env python3
"""
Script de orquestração do pipeline de validação (CI/CD Local).
Executa: Validação Estrutural -> Security Scan -> Terraform Plan.
"""

import os
import re
import sys
import subprocess
import shlex
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

# Adiciona a raiz do projeto ao path para imports
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common

console = common.console


def run_step(name, command, ignore_error=False):
    console.print(f"\n[bold cyan]🚀 Executando etapa: {name}[/]")
    try:
        # shell=True permite usar comandos do sistema
        subprocess.run(command, shell=True, check=True, text=True)
        console.print(f"[bold green]✅ {name} concluído com sucesso![/]")
        return True
    except subprocess.CalledProcessError:
        console.print(f"[bold red]❌ Falha na etapa: {name}[/]")
        if not ignore_error:
            console.print("[red]⛔ Pipeline interrompido devido a erro crítico.[/]")
            sys.exit(1)
        return False


def check_docker_health():
    """Verifica se o Docker Daemon está rodando antes de iniciar."""
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        console.print("[bold red]❌ Erro Crítico: Docker não está rodando ou não está instalado.[/]")
        console.print("[dim]O pipeline depende do Docker para rodar o sandbox de segurança.[/dim]")
        sys.exit(1)

def main():
    console.rule("[bold magenta]🔄 A-PONTE Workflow Pipeline[/]")

    # Determina o contexto
    project = os.environ.get("TF_VAR_project_name")
    if not project or project == "home":
        try:
            project = common.read_context()
        except:
            project = "home"

    if project == "home":
        console.print(
            "[red]❌ Erro: Pipeline não pode ser executado no contexto 'home'. Selecione um projeto.[/]"
        )
        sys.exit(1)

    # Fail Fast: Verifica dependências
    check_docker_health()

    # SECURITY FIX: Validação de Input para evitar Shell Injection em target_dir
    if not re.match(r"^[a-zA-Z0-9-_]+$", project):
        console.print(f"[red]❌ Erro: Nome de projeto inválido '{project}'. Use apenas letras, números, hífens e underscores.[/]")
        sys.exit(1)

    # Garante Account ID para Terragrunt (necessário para bucket name)
    if "TF_VAR_account_id" not in os.environ:
        try:
            # Tenta recuperar via AWS CLI se não estiver injetado
            acc = subprocess.check_output(["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"], text=True).strip()
            os.environ["TF_VAR_account_id"] = acc
            console.print(f"[dim]🆔 Account ID injetado: {acc}[/dim]")
        except Exception:
            console.print("[yellow]⚠️  Aviso: Não foi possível detectar AWS Account ID. O plan pode falhar.[/]")

    console.print(f"[dim]🎯 Projeto Alvo: [bold white]{project}[/][/dim]")

    # Define diretório alvo
    if project == "a-ponte":
        target_dir = "infrastructure/bootstrap"
    else:
        target_dir = f"projects/{project}"

    if not Path(target_dir).exists():
        console.print(f"[red]❌ Diretório não encontrado: {target_dir}[/]")
        sys.exit(1)

    # FIX: Usa container efêmero e único por execução para evitar Race Condition em CI/Paralelo
    container_name = f"mcp-tf-{os.getpid()}"

    # Tenta obter a imagem do container padrão ou usa default
    try:
        image = subprocess.check_output("docker inspect --format='{{.Config.Image}}' mcp-terraform", shell=True, text=True).strip()
    except:
        image = os.getenv("APONTE_MCP_IMAGE", "aponte-mcp-terraform:latest")

    console.print(f"[dim]🐳 Iniciando container isolado: {container_name}[/dim]")
    container_started = False
    try:
        # FIX: Windows Compatibility for Volume Mounting (Double Quotes work on both cmd and bash)
        vol_mount = f'"{project_root}:/app"'

        # FIX: Mount AWS credentials if available to support SSO/Profiles
        aws_mount = ""
        aws_home = Path.home() / ".aws"
        if aws_home.exists():
            aws_mount = f'-v "{aws_home}:/root/.aws:ro"'

        subprocess.run(
            f"docker run -d --rm --name {container_name} --label aponte.pipeline=true -v {vol_mount} {aws_mount} -w /app --entrypoint tail {image} -f /dev/null",
            shell=True, check=True, stdout=subprocess.DEVNULL
        )
        container_started = True

        # FIX: Limpeza via Docker para resolver 'Permission denied' em arquivos criados pelo Sandbox (root)
        console.print("[dim]🧹 Limpando caches (.terraform) via Docker para corrigir permissões...[/dim]")
        # Monta a raiz do projeto em /wd e limpa o diretório alvo
        subprocess.run(
            f"docker exec -w /app {container_name} rm -rf {target_dir}/.terraform {target_dir}/.terragrunt-cache",
            shell=True, stderr=subprocess.DEVNULL, check=False
        )

        # OTIMIZAÇÃO: Configura Cache de Plugins Terraform (Evita download repetitivo)
        # Usa um diretório dentro do projeto (.aponte-versions) que é persistente via mount /app
        cache_host_path = project_root / ".aponte-versions" / "tf-plugin-cache"
        cache_host_path.mkdir(parents=True, exist_ok=True)

        # Prepara variáveis de ambiente para o container
        docker_env = f" -e TF_VAR_project_name={project} -e TF_PLUGIN_CACHE_DIR=/app/.aponte-versions/tf-plugin-cache"

        # FIX: Garante que credenciais AWS estejam disponíveis no ambiente para serem repassadas
        # Se o usuário usa ~/.aws/credentials, elas não estão em os.environ por padrão.
        if "AWS_ACCESS_KEY_ID" not in os.environ:
            try:
                import boto3
                session = boto3.Session()
                creds = session.get_credentials()
                if creds:
                    frozen = creds.get_frozen_credentials()
                    if frozen:
                        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
                        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
                        if frozen.token:
                            os.environ["AWS_SESSION_TOKEN"] = frozen.token
                        if session.region_name and "AWS_REGION" not in os.environ:
                            os.environ["AWS_REGION"] = session.region_name
                        console.print("[dim]🔑 Credenciais AWS recuperadas do host via Boto3.[/dim]")
            except Exception:
                pass

        # FIX: Forward AWS credentials so get_aws_account_id() works inside the container
        env_vars_to_pass = [
            "TF_VAR_account_id", "TF_VAR_aws_region", "TF_VAR_security_email",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE", "AWS_CONFIG_FILE"
        ]
        for key in env_vars_to_pass:
            if key in os.environ:
                val = os.environ[key]
                # FIX: Windows cmd.exe doesn't handle single quotes from shlex.quote correctly
                if sys.platform == "win32":
                    quoted_val = f'"{val}"' if " " in val else val
                else:
                    quoted_val = shlex.quote(val)
                docker_env += f" -e {key}={quoted_val}"

        # 1. Validação Estrutural (Linting de arquivos e pastas)
        # Executa fmt na raiz (/app) e validate no diretório alvo
        run_step("Terraform Fmt", f"docker exec {docker_env} -w /app {container_name} terraform fmt -recursive")

        # Init com Retry (Resiliência contra falhas de rede/cache)
        init_cmd = f"docker exec {docker_env} -w /app {container_name} sh -c 'cd /app/{target_dir} && terraform init -backend=false'"
        if not run_step("Terraform Init", init_cmd, ignore_error=True):
            console.print("[yellow]⚠️  Falha no Init. Tentando limpar cache local e reiniciar...[/]")
            subprocess.run(f"docker exec -w /app {container_name} rm -rf {target_dir}/.terraform", shell=True)
            if not run_step("Terraform Init (Retry)", init_cmd):
                console.print("[red]⛔ Falha crítica no Terraform Init.[/]")
                sys.exit(1)

        run_step("Terraform Validate", f"docker exec {docker_env} -w /app {container_name} sh -c 'cd /app/{target_dir} && terraform validate'")

        # 2. Auditoria de Segurança (SAST)
        # Em dev, permitimos falhas (ignore_error=True) para não travar o fluxo, mas mostramos os alertas
        # Roda o ingestor completo para centralizar todos os resultados (Checkov, Trivy, etc)
        run_step("Security Scan (Unified)", f"docker exec {docker_env} -w /app {container_name} python3 core/services/security_ingestor.py --project {project}", ignore_error=True)

        # FIX: Limpa cache do Terraform (.terraform) antes do Terragrunt Plan.
        # O 'terraform init -backend=false' anterior cria um estado local que conflita
        # com o backend S3 gerenciado pelo Terragrunt. Forçamos um re-init limpo.
        console.print("[dim]🧹 Limpando estado local temporário antes do Plan...[/dim]")
        subprocess.run(f"docker exec -w /app {container_name} rm -rf {target_dir}/.terraform", shell=True, check=False)

        # 3. Terraform Plan (Dry-Run)
        # Verifica se as mudanças são válidas na AWS
        run_step("Terraform Plan", f"docker exec {docker_env} -w /app {container_name} sh -c 'cd /app/{target_dir} && terragrunt plan'")

    except subprocess.CalledProcessError:
        console.print("[red]❌ Falha na execução do pipeline.[/]")
        sys.exit(1)
    finally:
        if container_started:
            # FIX: Garante limpeza de arquivos root-owned mesmo em caso de falha/crash
            console.print("[dim]🧹 Finalizando pipeline e limpando artefatos...[/dim]")
            subprocess.run(
                f"docker exec -w /app {container_name} rm -rf {target_dir}/.terraform {target_dir}/.terragrunt-cache",
                shell=True, stderr=subprocess.DEVNULL, check=False
            )
            # Mata o container efêmero
            subprocess.run(f"docker rm -f {container_name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

            # FIX: Corrige permissões do cache de plugins (root -> user) para evitar arquivos bloqueados no host
            if sys.platform != "win32":
                uid = os.getuid()
                gid = os.getgid()
                subprocess.run(
                    f"docker run --rm -v '{project_root}:/app' {image} chown -R {uid}:{gid} /app/.aponte-versions/tf-plugin-cache /app/logs",
                    shell=True, stderr=subprocess.DEVNULL, check=False
                )

    console.print(
        Panel(
            "[bold green]🎉 Pipeline Finalizado com Sucesso![/]\n[dim]O código está pronto para deploy ou commit.[/dim]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
