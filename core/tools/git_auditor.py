#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.parse
import tempfile
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup paths (Robustez para execução direta)
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from botocore.config import Config
from rich.panel import Panel
from rich.prompt import Prompt

from core.agents import auditor as security_auditor
from core.domain import prompts as system_context
from core.lib import aws
from core.lib import toolbelt as tools
from core.lib import utils as common
from core.services import llm_gateway as llm_client
from core.services import versioning

try:
    import portalocker
except ImportError:
    portalocker = None

# Tenta carregar variáveis do .env (Suporte a execução direta)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[2] / ".env")
except ImportError:
    pass

# Tenta carregar chave do Infracost da configuração local (Suporte a CLI Tokens)
if "INFRACOST_API_KEY" not in os.environ:
    try:
        creds_path = Path.home() / ".config" / "infracost" / "credentials.yml"
        if creds_path.exists():
            with open(creds_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "api_key" in line and ":" in line:
                        os.environ["INFRACOST_API_KEY"] = line.split(":", 1)[1].strip()
                        break
    except Exception:
        pass

# Lista de diretórios para ignorar durante a varredura (Economia de CPU/Tokens)
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".terraform",
    ".terragrunt-cache",
    ".aponte-versions",
    ".aponte",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    "target",
    "output",
    "vendor",
    "bin",
    "obj",
    ".idea",
    ".vscode",
}

def load_excluded_dirs():
    """Carrega diretórios excluídos do .aponteignore ou usa defaults."""
    try:
        root = common.get_project_root()
        ignore_file = root / ".aponteignore"
        if ignore_file.exists():
            with open(ignore_file, "r", encoding="utf-8") as f:
                custom = {line.strip() for line in f if line.strip() and not line.startswith("#")}
            return DEFAULT_EXCLUDED_DIRS.union(custom)
    except Exception:
        pass
    return DEFAULT_EXCLUDED_DIRS

EXCLUDED_DIRS = load_excluded_dirs()

# Memória de Contexto entre Repositórios (App -> Infra)
APP_STACK_MEMORY = {}

# Template do Workflow de Governança
GOVERNANCE_WORKFLOW_TEMPLATE = """name: A-PONTE Governance

on: [push, pull_request]

jobs:
  compliance:
    name: Compliance Check
    uses: {governance_repo}/.github/workflows/reusable-compliance.yml@main
    with:
      project_name: "{repo_name}"
    secrets: inherit
"""

VARIABLE_CONTRACT = """
    MAPA DE VARIÁVEIS E TAGGING (CONTRATO OBRIGATÓRIO):
    1. var.project_name: ID do tenant (Backend). Use como prefixo em nomes de recursos.
    2. var.resource_name: Nome do componente/recurso principal (ex: web-server). Use na tag 'Component'.
    3. var.app_name: Nome da aplicação (sites / aplicativos). Use na tag 'Application'.
    4. var.environment: Ambiente (dev / prod). Use na tag 'Environment'.
    5. var.aws_region: Região AWS (ex: sa-east-1).
    6. var.account_id: ID da conta AWS.

    ESTRATÉGIA DE TAGGING:
       - Se o recurso não suportar nome dinâmico ou for um recurso lógico (ex: VPC, Subnet, SG), OBRIGATÓRIO usar tags:
         tags = { Name = "${var.project_name}-logico", App = var.app_name, Env = var.environment, Component = var.resource_name }
       - Nunca use strings hardcoded para ambiente ou nome de projeto. Use as variáveis.
    7. PROPRIEDADE E REDE (VPC/EC2/ECR):
       - O 'Dono' da VPC e recursos é definido por `var.project_name`.
       - Nomes de recursos de rede devem seguir: `${var.project_name}-vpc`, `${var.project_name}-sg-ec2`.
       - Conectividade EC2 -> ECR: Se usar EC2/ECS privado, sugira VPC Endpoints ou garanta rotas NAT, mantendo o prefixo do projeto nos SGs.
    8. ESTRATÉGIA DE COMPOSIÇÃO (MODULE-FIRST):
       - Não reinvente a roda. Para componentes complexos (VPC, RDS, EKS), sugira o uso de `module "..."`.
       - Apenas escreva `resource "..."` para componentes simples ou colas (Glue code).
    """

def parse_dockerfile_requirements(file_path: Path) -> str:
    """
    Extrai deterministicamente requisitos de infraestrutura do Dockerfile.
    Isso ajuda a IA a não 'alucinar' portas ou variáveis.
    """
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        requirements = []

        # 1. Detecta Portas (EXPOSE) -> Load Balancer / Security Group
        # Captura EXPOSE 80, EXPOSE 80/tcp, EXPOSE 80 443
        # FIX: Suporta indentação (^\s*) para Dockerfiles formatados
        exposed_lines = re.findall(r"^\s*EXPOSE\s+(.+)", content, re.MULTILINE)
        ports = []
        for line in exposed_lines:
            parts = line.split()
            for p in parts:
                port = p.split("/")[0]  # Remove /tcp ou /udp
                if port.isdigit():
                    ports.append(port)
        if ports:
            requirements.append(f"- PORTAS EXPOSTAS (ALB/SG): {', '.join(ports)}")

        # 2. Detecta Variáveis de Ambiente (ENV) -> SSM Parameter Store
        # Captura ENV VAR_NAME ou ENV VAR_NAME=valor
        # FIX: Suporta indentação (^\s*)
        env_vars = re.findall(r"^\s*ENV\s+([a-zA-Z0-9_]+)", content, re.MULTILINE | re.IGNORECASE)
        if env_vars:
            requirements.append(f"- VARIÁVEIS DE AMBIENTE (SSM): {', '.join(env_vars)}")

        if requirements:
            return "\n".join(requirements)
    except Exception as e:
        common.log_warning(f"Erro ao ler Dockerfile ({file_path.name}): {e}")
    return ""


def detect_stack_info(repo_structure: str, base_path: Path = None) -> str:
    """Usa IA para resumir a stack do App e passar para a Infra."""

    readme_context = ""
    if base_path:
        try:
            # Busca README de forma case-insensitive para capturar contexto de negócio
            for f in base_path.iterdir():
                if f.is_file() and f.name.lower().startswith("readme"):
                    readme_context = f"\nCONTEXTO DO README (Resumo):\n{f.read_text(encoding='utf-8', errors='ignore')[:3000]}\n"
                    break
        except Exception:
            pass

    prompt = f"""
    {system_context.APONTE_CONTEXT}

    Analise a lista de arquivos e o README abaixo para identificar a Stack Tecnológica e o TIPO de aplicação (Site, API, App Mobile, CLI).
    Seja ultra-breve (1 frase). Ex: "App Android (Kotlin) com Firebase" ou "Site Estático (React) no S3".

    ARQUIVOS:
    {repo_structure}

    {readme_context}
    """
    return llm_client.generate(prompt, verbose=False) or ""


def is_excluded(path: Path) -> bool:
    """Verifica se o arquivo está em um diretório excluído."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def get_linked_repos(project_name):
    """Recupera a lista de repositórios vinculados ao projeto."""
    root_dir = common.get_project_root()
    repos = []

    # Carrega metadados de tipo (app/infra)
    meta_file = root_dir / "projects" / f"{project_name}.repos_meta.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
        except Exception as e:
            common.log_warning(f"Metadados corrompidos em {meta_file.name}: {e}")

    # 1. Tenta via variável de ambiente (TF_VAR_github_repos)
    env_repos = os.getenv("TF_VAR_github_repos")
    if env_repos:
        try:
            repos = json.loads(env_repos)
        except Exception as e:
            common.log_warning(f"Falha ao decodificar TF_VAR_github_repos: {e}")

    # 2. Tenta via arquivo .repos
    if not repos:
        repos_file = root_dir / "projects" / f"{project_name}.repos"
        if repos_file.exists():
            try:
                with open(repos_file) as f:
                    for line in f:
                        # Remove comentários inline e espaços
                        clean_line = line.split("#", 1)[0].strip()
                        if clean_line:
                            repos.append(clean_line)
            except Exception as e:
                common.log_warning(f"Falha ao ler arquivo de repositórios {repos_file.name}: {e}")

    # Retorna lista de tuplas (nome, tipo)
    repo_list = [(r, meta.get(r, "unknown")) for r in repos]

    # Ordenação Estratégica: App primeiro (0) para definir requisitos, depois Infra (1)
    repo_list.sort(key=lambda x: {"app": 0, "infra": 1}.get(x[1], 2))

    return repo_list


def remove_readonly(func, path, _):
    """Helper para remover arquivos read-only no Windows (Git objects)."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_tfsec_report(path: Path) -> str:
    """Executa tfsec para identificar vulnerabilidades de segurança (SAST)."""
    # Tenta executar via Docker (Sandbox) primeiro
    try:
        root = common.get_project_root()
        if path.resolve().is_relative_to(root.resolve()):
            rel_path = path.resolve().relative_to(root.resolve())
            # Verifica se container está rodando
            if subprocess.run(["docker", "ps", "-q", "-f", "name=mcp-terraform"], capture_output=True).returncode == 0:
                result = subprocess.run(
                    ["docker", "exec", "mcp-terraform", "tfsec", f"/app/{rel_path}", "--no-color", "--format", "text", "--soft-fail"],
                    capture_output=True, text=True, check=False
                )
                if result.stdout and "No problems detected" not in result.stdout:
                    return f"\n[RELATÓRIO TFSEC - VULNERABILIDADES (Sandbox)]:\n{result.stdout}"
    except Exception as e:
        common.log_warning(f"Falha ao executar tfsec (Sandbox): {e}")

    # Fallback local
    if shutil.which("tfsec") is None:
        return ""

    try:
        result = subprocess.run(["tfsec", str(path), "--no-color", "--format", "text", "--soft-fail"], capture_output=True, text=True, check=False, timeout=300)

        if result.stdout and "No problems detected" not in result.stdout:
            # Limita o tamanho para não estourar o contexto da IA
            return f"\n[RELATÓRIO TFSEC - VULNERABILIDADES]:\n{result.stdout}"
    except subprocess.TimeoutExpired:
        return "\n[RELATÓRIO TFSEC]: Timeout excedido (300s)."
    except Exception as e:
        common.log_warning(f"Falha ao executar tfsec (Local): {e}")
    return ""


def save_alignment_event(repo: str, file_name: str, analysis: str):
    """Salva o evento de alinhamento no histórico central (Cérebro Compartilhado)."""
    timestamp = datetime.now().isoformat()
    project = common.read_context()

    if not project:
        common.log_warning("Contexto do projeto não definido. Evento de alinhamento não será salvo.")
        return

    try:
        retry_config = Config(retries={"max_attempts": 10, "mode": "adaptive"})
        dynamodb = aws.get_session().resource("dynamodb", config=retry_config)
        table = dynamodb.Table(aws.AI_HISTORY_TABLE)
        item = {
            "ProjectName": project,
            "Timestamp": timestamp,
            "ErrorSnippet": f"Git Alignment: {repo}/{file_name}",
            "Analysis": analysis[:1000],
            "Author": aws.get_current_user(),
            "Action": "Architected",
        }
        table.put_item(Item=item)
    except Exception as e:
        common.log_warning(f"Falha ao salvar memória de alinhamento (DynamoDB): {e}")


def save_alignment_report(repo_name, file_name, analysis):
    """Salva o relatório de alinhamento em arquivo local para centralização de logs."""
    try:
        log_dir = common.get_project_root() / "logs" / "audits"
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Sanitiza nome do arquivo
        safe_file = file_name.replace("/", "_").replace("\\", "_")
        safe_repo = repo_name.replace("/", "_").replace("\\", "_")

        filename = log_dir / f"alignment_{safe_repo}_{safe_file}_{timestamp}.md"

        content = f"# Relatório de Alinhamento: {repo_name}/{file_name}\n"
        content += f"**Data:** {timestamp}\n"
        content += f"**Arquivo:** {file_name}\n\n"
        content += analysis

        filename.write_text(content, encoding="utf-8")
    except Exception as e:
        common.log_warning(f"Falha ao salvar relatório de alinhamento em logs: {e}")


def check_governance_workflow(path: Path, repo_name: str, mode: str) -> bool:
    """Verifica e injeta o Workflow de Governança (Reusable) nos repositórios vinculados."""
    workflow_dir = path / ".github" / "workflows"
    workflow_file = workflow_dir / "aponte-governance.yml"

    # Template que chama o Workflow Reutilizável Centralizado
    # O repositório central pode ser configurado via variável de ambiente.
    governance_repo = os.getenv("A_PONTE_GOVERNANCE_REPO", "aponte-platform/A-PONTE")
    content = GOVERNANCE_WORKFLOW_TEMPLATE.format(
        governance_repo=governance_repo,
        repo_name=repo_name
    )

    if workflow_file.exists():
        # Verifica se o conteúdo está atualizado (Drift Detection)
        try:
            existing_content = workflow_file.read_text(encoding="utf-8")
            # Normaliza quebras de linha e espaços para comparação
            if existing_content.strip() == content.strip():
                return True

            common.console.print(f"\n[bold yellow]⚠️  Workflow de Governança desatualizado em {repo_name}.[/]")
        except Exception as e:
            common.log_warning(f"Erro ao ler workflow existente em {repo_name}: {e}")
            # Continua execução para tentar recriar/atualizar
    else:
        common.console.print(
            f"\n[bold yellow]⚠️  Workflow de Governança ausente em {repo_name}.[/]"
        )

    if (
        mode == "interactive"
        and Prompt.ask(
            f"Deseja instalar/atualizar o workflow de governança em {repo_name}?",
            choices=["s", "n"],
            default="s",
        )
        == "s"
    ):
        try:
            workflow_dir.mkdir(parents=True, exist_ok=True)
            workflow_file.write_text(content, encoding="utf-8")
            common.log_success(
                f"Governança injetada em .github/workflows/aponte-governance.yml"
            )
            return True
        except Exception as e:
            common.log_error(f"Falha ao injetar workflow de governança: {e}")
            return False
    return False


def analyze_alignment(
    file_path: Path,
    category: str,
    repo_name: str,
    repo_type: str,
    mode: str = "interactive",
    repo_structure: str = "",
    app_context: str = "",
    root_path: Path = None,
) -> bool:
    """Usa a IA para verificar alinhamento arquitetural de arquivos não-Terraform."""
    # Throttling preventivo para evitar 429 (Resource Exhausted)
    time.sleep(5)

    try:
        # Atomic Read com Lock Compartilhado (SH) para evitar leitura de escrita parcial
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            try:
                if portalocker:
                    portalocker.lock(f, portalocker.LOCK_SH)
                content = f.read()
            finally:
                if portalocker:
                    portalocker.unlock(f)
    except Exception as e:
        common.log_warning(f"Falha ao ler arquivo para análise ({file_path.name}): {e}")
        return False

    # Tenta ler documentação para enriquecer contexto (Refinamento do Usuário)
    docs_context = system_context.load_docs_context()

    # Validação Determinística de App (Hadolint)
    app_report = ""
    if file_path.name == "Dockerfile":
        app_report = tools.get_hadolint_report(file_path)

    # Extração Determinística de Requisitos (Dockerfile)
    docker_requirements = ""
    if file_path.name == "Dockerfile":
        docker_requirements = parse_dockerfile_requirements(file_path)

    # Define objetivos e formato de resposta baseado no tipo de repositório
    if repo_type == "app":
        objective_block = """
    OBJETIVO (Extração de Intenção - No-Code Generation):
    1. ANÁLISE DE REQUISITOS: Identificar a Stack Tecnológica e o que a aplicação precisa para rodar (Docker? BD? S3? Redis?).
    2. EXTRAÇÃO ESTRUTURADA: Em vez de escrever código Terraform (que pode alucinar), preencha um JSON com os requisitos.
    3. CONTEXTO DE ARQUIVO: Se estiver analisando um `Dockerfile`, foque em portas (EXPOSE) e volumes. Se for `requirements.txt`, foque em bibliotecas de nuvem (boto3, s3fs).
    4. NÃO CORRIGIR CÓDIGO DE APLICAÇÃO: Não altere a lógica do código fonte.
    """
        response_format = """
    RESPOSTA OBRIGATÓRIA (JSON):

    ```json
    {
      "stack": "python-flask", // ou java-spring, node-express, etc.
      "database": ["postgres"], // lista de dbs: postgres, mysql, dynamo, none
      "cache": ["redis"], // lista de caches: redis, memcached, none
      "exposure": "public-alb", // public-alb, private-alb, worker (sem exposição)
      "ports": [8080], // portas container
      "storage": ["s3"], // s3, efs, none
      "dependencies": ["sqs"] // outros serviços aws
    }
    ```
    """
    else:
        objective_block = """
    OBJETIVO (Montar o Quebra-Cabeça):
    1. Se for INFRA: Validar se o código segue as práticas da A-PONTE (Terragrunt, Tags, UserData seguro).
       - VERIFICAÇÃO CRÍTICA: Garantir que não existam recursos de bootstrap (S3 Backend/DynamoDB Lock) hardcoded. Isso viola o ADR-003.
       - REMOÇÃO DE BACKEND: O Terragrunt gerencia o estado. Se encontrar `terraform { backend "s3" ... }`, REMOVA esse bloco. Manter isso causa erro fatal.
       - PADRONIZAÇÃO: Substitua nomes fixos por `${var.project_name}` para suportar Multi-Tenancy.
       - GROUNDING: Se o arquivo for `backend.tf` gerado automaticamente, ignore regras de Security Group ou SSH. Apenas valide a sintaxe.
    2. CORREÇÃO (Auto-Fix): Se encontrar erros de segurança, hardcoded credentials ou más práticas (ex: user_data sem log, Dockerfile root), CORRIJA o arquivo original aplicando as diretrizes do WORKFLOW e ADR acima.
    """
        response_format = f"""
    RESPOSTA OBRIGATÓRIA:

    ### Análise
    [Liste os erros encontrados e as correções aplicadas. Seja direto.]

    ### Correção do Arquivo
    (Se houver correções, forneça o código COMPLETO do arquivo '{file_path.name}'. NÃO use '...' ou resumos. O código deve estar pronto para produção.)
    ```{file_path.suffix.replace('.', '') if file_path.suffix else 'text'}
    [Conteúdo COMPLETO e CORRIGIDO do arquivo]
    ```

    ### Sugestão de Infraestrutura (Terraform)
    (Gere o código HCL completo para suportar este App na AWS. Inclua Resource, IAM, SG e SSM.)
    ```hcl
    // Recursos sugeridos para suportar {file_path.name}
    ...
    ```
    """

    # Truncate inputs to prevent LLM timeouts
    repo_structure = (repo_structure[:4000] + "... (truncated)") if len(repo_structure) > 4000 else repo_structure
    app_report = (app_report[:3000] + "... (truncated)") if len(app_report) > 3000 else app_report

    prompt = f"""
    {system_context.APONTE_CONTEXT}

    {docs_context}

    ESTRUTURA DE ARQUIVOS DO PROJETO (Visão Periférica):
    {repo_structure}

    {app_context}

    Atue como um Arquiteto de Soluções Cloud (DevSecOps) especialista na plataforma A-PONTE.

    IMPORTANTE: Você é uma engine de refatoração de código. Seja direto e técnico.
    Evite "textão". Foque no código.
    GROUNDING: Apenas aponte erros que REALMENTE existem no código abaixo. Se estiver tudo certo, não invente problemas.
    ANTI-ALUCINAÇÃO: Não repita os exemplos de treinamento se eles não se aplicarem ao código atual.

    {VARIABLE_CONTRACT}

    {security_auditor.SECURITY_DIRECTIVE}

    {app_report}

    REQUISITOS DETERMINÍSTICOS DETECTADOS (DOCKERFILE):
    {docker_requirements}

    Analise o arquivo '{file_path.name}' do tipo '{category}'.
    CONTEXTO DO REPOSITÓRIO: Tipo '{repo_type}' (App = Aplicação de Negócio, Infra = Módulos/IaC).

    🚨 DIRETRIZ MANDATÓRIA:
    - O ambiente é 100% AWS.
    - PROIBIDO sugerir serviços de Azure (AKS, Blob Storage, Azure DevOps) ou GCP.
    - Use apenas terminologia e serviços AWS (EKS, S3, CodePipeline/GitHub Actions).

    {objective_block}

    VERIFICAÇÕES:
    1. Credenciais: Existem chaves hardcoded? (Erro Crítico).
    2. Pipeline (se aplicável): Usa OIDC (aws-actions/configure-aws-credentials)?
    3. App/Docker (se aplicável): Indica necessidade de ECR, ECS, RDS?
    4. Scripts/UserData: Instala pacotes que deveriam estar na AMI (Packer)?
    5. Segurança: Dockerfile usa user root? UserData expõe segredos?
       - Se houver RELATÓRIO HADOLINT acima, corrija OBRIGATORIAMENTE os erros apontados (ex: fixar versões, não usar root).
    6. Service Discovery (SSM - ADR-015):
       - INFRA: O código exporta endpoints (DB, API) para o SSM Parameter Store? (Padrão: /{{project}}/{{env}}/{{service}}/{{key}})
       - APP: O código espera configurações via variáveis de ambiente? Sugira injeção via SSM na infraestrutura.
       - CONTEXTO: Use a lista de arquivos acima para inferir a stack (Ex: pom.xml = Java, requirements.txt = Python) e ajustar a sugestão.
       - DOCKER: Se houver 'PORTAS EXPOSTAS' detectadas acima, crie o Security Group liberando essas portas e sugira um ALB se for HTTP (80/443/8080).
    7. IAM Permissions:
       - INFRA: O recurso de computação (EC2/ECS/Lambda) tem permissão 'ssm:GetParameter' para ler as configs do projeto?
    8. GERAÇÃO DE INFRAESTRUTURA (Cenário App -> Infra):
       - Se estiver analisando um APP (ex: Dockerfile, package.json), gere o código Terraform necessário para hospedá-lo.
       - Exemplo: Dockerfile -> Requer ECR (Repo) + ECS/EC2 (Compute) + IAM Role (Execution) + Security Group.
       - O código gerado deve ser COMPLETO, incluindo variáveis e outputs.
       - Siga o ADR-015: Exporte os endpoints gerados (ex: ECR URL) para o SSM.
    9. ISOLAMENTO DE REDE E NOMENCLATURA (EC2/ECR/S3):
       - Ao conectar EC2 e ECR, garanta que ambos pertençam ao mesmo `var.project_name`.
       - S3: Buckets devem ter prefixo `${{var.project_name}}-`.
       - ECR: Repositórios devem ser criados via Terraform se o App precisar.
       - Valide se a VPC sugerida ou existente tem o prefixo correto no `Name`.
    10. KMS REMOVAL: Não sugira nem permita `aws_kms_key`. Use criptografia gerenciada pela AWS (AES256).

    CONTEÚDO:
    ```text
    {content}
    ```

    {response_format}
    """

    common.console.print(f"[dim]🧠 Analisando {category}: {file_path.name}...[/dim]")
    try:
        # Enforce local provider by default, but allow override via env var
        audit_provider = os.getenv("APONTE_AUDIT_PROVIDER", "ollama")
        response = llm_client.generate(prompt, verbose=True, provider=audit_provider)
    except Exception as e:
        common.log_warning(f"Falha na análise de IA para {file_path.name}: {e}")
        return False

    # Calcula caminho relativo para relatório (Contexto de Diretório)
    rel_path_str = file_path.name
    if root_path:
        try:
            rel_path_str = str(file_path.relative_to(root_path))
        except ValueError:
            pass

    if response:
        # 1. Persiste no Cérebro
        save_alignment_event(repo_name, rel_path_str, response)

        # 1.1 Persiste em Logs (Centralização)
        save_alignment_report(repo_name, rel_path_str, response)

        common.console.print(
            f"\n[bold cyan]📄 Relatório de Alinhamento ({file_path.name}):[/]"
        )

        # Exibe apenas a análise para não poluir, a menos que seja verbose
        analysis_match = re.search(
            r"### Análise\s*(.*?)\s*(###|$)", response, re.DOTALL
        )
        if analysis_match:
            common.console.print(analysis_match.group(1).strip())
        else:
            common.console.print(response)

        # 2. Lógica de Correção do Arquivo (Auto-Fix)
        # Regex flexível: Aceita variações como "Correção", "Fixed File", case-insensitive
        correction_match = re.search(
            r"### (?:Correção|Correction|Fixed).*?```(?:\w+)?\n(.*?)```",
            response,
            re.DOTALL | re.IGNORECASE,
        )
        if correction_match:
            fixed_content = correction_match.group(1).strip()

            # SAFETY CHECK: Valida se o Gemini não alucinou um arquivo vazio ou truncado
            # Melhora a heurística: detecta truncamento no final mesmo em arquivos longos
            if ("..." in fixed_content and len(fixed_content.splitlines()) < 5) or \
               (fixed_content.strip().endswith("...") and len(fixed_content) < len(content)):
                common.console.print(
                    "[bold red]❌ A IA retornou um arquivo truncado (...). Ignorando correção por segurança.[/]"
                )
            elif len(fixed_content) < len(content) * 0.5 and len(content) > 100:
                common.console.print(
                    "[bold red]❌ A IA retornou um arquivo suspeitosamente pequeno. Ignorando correção por segurança.[/]"
                )
            elif fixed_content and fixed_content != content.strip():
                if mode == "check":
                    common.console.print(f"[bold red]❌ Falha de Alinhamento: Correção sugerida para {file_path.name}.[/]")
                    return True

                common.console.print(
                    f"\n[bold yellow]🔧 A IA sugeriu correções para {file_path.name}.[/]"
                )
                if (
                    Prompt.ask(
                        f"Deseja aplicar a correção em {file_path.name}?",
                        choices=["s", "n"],
                        default="n",
                    )
                    == "s"
                ):
                    # Cria backup versionado antes de aplicar (Safety Net)
                    try:
                        project = common.read_context()
                        v_id = versioning.version_generic_file(
                            file_path, project, reason="Pre-AI-Fix (Git Audit)"
                        )
                        common.console.print(f"[dim]Backup criado: {v_id}[/dim]")
                    except Exception as e:
                        common.log_error(f"Falha ao criar backup de segurança: {e}. Abortando correção.")
                        return False

                    # Atomic Write com Lock Exclusivo (EX)
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            try:
                                if portalocker:
                                    portalocker.lock(f, portalocker.LOCK_EX)
                                f.write(fixed_content)
                                common.log_success(f"Arquivo {file_path.name} atualizado!")
                            finally:
                                if portalocker:
                                    portalocker.unlock(f)
                    except Exception as e:
                        common.log_error(f"Falha ao aplicar correção em {file_path.name}: {e}")

        # 3. Extrai e Oferece Código Infra (Terraform ou JSON de Requisitos)
        if repo_type == "app":
            json_match = re.search(r"```json\n(.*?)\n```", response, re.DOTALL)
            if json_match:
                requirements = json_match.group(1).strip()
                common.console.print(Panel(requirements, title="📋 Requisitos Extraídos (JSON)", border_style="cyan"))

                if mode == "interactive" and Prompt.ask("[bold green]🤖 Deseja salvar estes requisitos para o Construtor?[/]", choices=["s", "n"], default="s") == "s":
                    root = common.get_project_root()
                    project = common.read_context()
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    artifacts_dir = root / ".aponte-versions" / "ia_ops_artifacts" / project / timestamp
                    artifacts_dir.mkdir(parents=True, exist_ok=True)

                    # FIX: Usa nome único (pai + arquivo) para evitar colisão em monorepos
                    dest_file = artifacts_dir / f"requirements_{file_path.parent.name}_{file_path.name}.json"
                    try:
                        with open(dest_file, "w", encoding="utf-8") as f:
                            f.write(requirements)

                        common.log_success(f"Requisitos salvos em: {dest_file}")
                        common.console.print("[dim]Próximo passo: O Construtor usará este JSON para montar a infraestrutura com módulos validados.[/dim]")
                    except Exception as e:
                        common.log_error(f"Falha ao salvar artefatos JSON: {e}")
        else:
            # Regex melhorada: Aceita 'tf', espaços extras ou quebra de linha imediata
            hcl_match = re.search(
                r"### Sugestão de Infraestrutura.*?```(?:hcl|terraform|tf)?.*?\n(.*?)```",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if hcl_match:
                code = hcl_match.group(1).strip()
                if code:
                    # Sanitização prévia (Remove alucinações do DeepSeek 1.5b)
                    code = tools.sanitize_hcl(code)

                    # Validação de Sintaxe (Sandbox) antes de oferecer
                    if not tools.validate_hcl_syntax(code):
                        common.console.print(
                            "[bold red]❌ A IA gerou sugestão de infraestrutura com sintaxe inválida. Descartada por segurança.[/]"
                        )
                        return False # Não falha o pipeline se a IA alucinar sintaxe

                    if (
                        mode == "interactive" and
                        Prompt.ask(
                            f"[bold green]🤖 A IA gerou infraestrutura para suportar este arquivo. Deseja salvar?[/]",
                            choices=["s", "n"],
                            default="n",
                        )
                        == "s"
                    ):
                        root = common.get_project_root()
                        project = common.read_context()
                        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

                        # Salva em artefatos estruturados (evita poluir workspace com arquivos aleatórios)
                        artifacts_dir = (
                            root
                            / ".aponte-versions"
                            / "ia_ops_artifacts"
                            / project
                            / timestamp
                        )
                        artifacts_dir.mkdir(parents=True, exist_ok=True)

                        safe_repo = repo_name.replace("/", "_").replace("-", "_")
                        # FIX: Adiciona nome do arquivo fonte para evitar sobrescrita
                        dest_file = artifacts_dir / f"req_{safe_repo}_{file_path.name}.tf"

                        try:
                            with open(dest_file, "w", encoding="utf-8") as f:
                                f.write(
                                    f"// Gerado via Git Audit de {repo_name}/{file_path.name}\n{code}"
                                )

                            common.log_success(f"Sugestão salva em: {dest_file}")
                            common.console.print(
                                f"[dim]Dica: Revise o arquivo em .aponte-versions e mova para infrastructure/ se aprovado.[/dim]"
                            )
                        except Exception as e:
                            common.log_error(f"Falha ao salvar sugestão de infraestrutura: {e}")
    else:
        common.console.print(
            f"[dim yellow]⚠️  Sem resposta da IA para {file_path.name}.[/dim]"
        )
    return False


def remove_hcl_comments(text: str) -> str:
    """Remove comentários HCL (//, #, /* ... */) preservando strings."""
    out = []
    i = 0
    n = len(text)
    in_string = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        c = text[i]

        if in_line_comment:
            if c == '\n':
                in_line_comment = False
                out.append(c)
            i += 1
            continue

        if in_block_comment:
            if c == '*' and i+1 < n and text[i+1] == '/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            out.append(c)
            if c == '"' and (i == 0 or text[i-1] != '\\'):
                in_string = False
            i += 1
            continue

        if c == '"':
            in_string = True
            out.append(c)
            i += 1
        elif c == '#' or (c == '/' and i+1 < n and text[i+1] == '/'):
            in_line_comment = True
            i += 1
        elif c == '/' and i+1 < n and text[i+1] == '*':
            in_block_comment = True
            i += 2
        else:
            out.append(c)
            i += 1

    return "".join(out)


def extract_terraform_variables(path: Path) -> dict:
    """
    Extrai variáveis declaradas nos arquivos .tf distinguindo obrigatórias de opcionais.
    Retorna: dict {'var_name': {'required': bool, 'description': str}}
    """
    variables = {}
    try:
        for tf_file in path.glob("*.tf"):
            content = tf_file.read_text(encoding="utf-8", errors="ignore")

            # Remove comentários de forma robusta antes de processar
            # Isso evita falsos positivos com variáveis comentadas
            clean_content = remove_hcl_comments(content)

            # Regex agora é seguro pois não há comentários
            var_blocks = re.finditer(r'variable\s*"([a-zA-Z0-9_-]+)"\s*\{', clean_content)

            for match in var_blocks:
                var_name = match.group(1)
                start_idx = match.end()

                # Busca o fechamento do bloco respeitando strings e comentários
                open_braces = 1
                block_content = ""

                for char in clean_content[start_idx:]:
                    if char == '{':
                        open_braces += 1
                    elif char == '}':
                        open_braces -= 1

                    if open_braces == 0:
                        break
                    block_content += char

                has_default = re.search(r'\bdefault\s*=', block_content) is not None

                variables[var_name] = {
                    "required": not has_default,
                    "has_default": has_default
                }

    except Exception as e:
        common.log_warning(f"Falha ao extrair variáveis de {path}: {e}")
    return variables


def ensure_tflint_config(path: Path):
    """Injeta configuração do TFLint se ausente."""
    config_path = path / ".tflint.hcl"

    # Verifica se precisa atualizar (Se não existe ou se está desatualizado/sem regras da casa)
    should_write = True
    if config_path.exists() and config_path.stat().st_size > 0:
        try:
            if "aws_resource_missing_tags" in config_path.read_text(encoding="utf-8"):
                should_write = False
        except Exception:
            pass

    if should_write:
        tflint_config = """
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

plugin "aws" {
    enabled = true
    version = "0.28.0"
    source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

config {
    module = true
    force = false
    disabled_by_default = false
}

# --- A-PONTE HOUSE RULES (GOVERNANÇA) ---

# 1. Variáveis devem ter tipos explícitos (Robustez)
rule "terraform_typed_variables" {
    enabled = true
}

# 2. Variáveis não usadas devem ser removidas (Limpeza)
rule "terraform_unused_declarations" {
    enabled = true
}

# 3. Convenção de Nomes (Snake Case padrão)
rule "terraform_naming_convention" {
    enabled = true
}

# 4. Tags Obrigatórias (FinOps & Multi-Tenant Isolation)
# Garante que todo recurso rastreável tenha as tags de contexto para isolamento de custo e lógica
rule "aws_resource_missing_tags" {
    enabled = true
    tags = ["Project", "Environment", "App", "Component", "ManagedBy"]
}
"""
        try:
            config_path.write_text(tflint_config, encoding="utf-8")
            # Tenta init local se possível
            if shutil.which("tflint"):
                # OTIMIZAÇÃO: Copia cache de plugins do projeto para evitar download repetitivo
                plugin_cache = common.get_project_root() / ".tflint.d"
                if plugin_cache.exists():
                    try:
                        shutil.copytree(plugin_cache, path / ".tflint.d", dirs_exist_ok=True)
                    except Exception:
                        pass

                subprocess.run(["tflint", "--init"], cwd=path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass


def audit_directory(
    path: Path, repo_name: str, repo_type: str, mode: str = "interactive"
) -> bool:
    """Audita e corrige um diretório local (já existente ou clonado)."""
    # Previne travamento solicitando credenciais no terminal
    git_env = os.environ.copy()
    git_env["GIT_TERMINAL_PROMPT"] = "0"

    success = True

    # 0. Validação Determinística de Segredos (Safety First)
    common.console.print("[dim]🔒 Executando Secret Scanning (Gitleaks)...[/dim]")
    if not tools.audit_gitleaks(path):
        common.console.print(f"[bold red]🚨 SEGREDOS DETECTADOS PELO GITLEAKS![/]")
        common.console.print(
            "[bold red]❌ Auditoria interrompida: Remova os segredos hardcoded antes de prosseguir.[/]"
        )
        return False

    # 0.0.1 Garante TFLint Config
    ensure_tflint_config(path)

    # 0.1 Injeção de Governança (CI/CD)
    # Garante que o repo tenha o workflow que chama o A-PONTE
    if not check_governance_workflow(path, repo_name, mode):
        if mode == "check":
            common.log_error(f"Falha de Governança: Workflow ausente em {repo_name}.")
            success = False

    # 1. Análise de Infraestrutura (Terraform)
    common.console.print(
        f"[bold magenta]🧠 Analisando Infraestrutura (Terraform)...[/]"
    )

    # FASE 0: Higiene Determinística (Terraform Fmt)
    # Garante que a IA leia código formatado, evitando alucinações por má indentação.
    try:
        common.console.print(
            "[dim]🧹 Executando 'terraform fmt' (Pre-Processing)...[/dim]"
        )

        # Tenta usar o Sandbox (MCP) se o path estiver dentro do projeto para garantir consistência
        use_docker = False
        root = common.get_project_root()
        if path.resolve().is_relative_to(root.resolve()):
            if (
                subprocess.run(
                    [
                        "docker",
                        "ps",
                        "-q",
                        "-f",
                        "name=mcp-terraform",
                        "-f",
                        "status=running",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
            ):
                use_docker = True

        if use_docker:
            rel_path = path.resolve().relative_to(root.resolve())
            container_path = f"/app/{rel_path}"
            res = subprocess.run(
                [
                    "docker",
                    "exec",
                    "mcp-terraform",
                    "terraform",
                    "fmt",
                    "-recursive",
                    container_path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            res = subprocess.run(
                ["terraform", "fmt", "-recursive", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

        if res.returncode != 0:
            common.console.print("[dim yellow]⚠️  Aviso: 'terraform fmt' encontrou erros de sintaxe. A análise pode ser afetada.[/]")
            if mode == "check":
                success = False
    except Exception as e:
        common.log_warning(f"Falha ao executar terraform fmt: {e}")
        if mode == "check":
            success = False

    # 0. Coleta Estrutura do Repositório (Contexto Global para a IA)
    repo_structure = ""
    try:
        files_list = []

        # FIX: Suporte nativo a .gitignore via git ls-files
        # Isso evita ler arquivos desnecessários e respeita as regras do projeto
        is_git_repo = False
        if shutil.which("git"):
            if (path / ".git").exists():
                is_git_repo = True
            else:
                # Verifica se está dentro de uma work tree (para subdiretórios)
                res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, capture_output=True)
                if res.returncode == 0:
                    is_git_repo = True

        if is_git_repo:
            res = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=path, capture_output=True, text=True)
            if res.returncode == 0:
                files_list = [f for f in res.stdout.splitlines() if not is_excluded(Path(f))]

        if not files_list:
            for p in path.rglob("*"):
                if p.is_file() and not is_excluded(p):
                    files_list.append(str(p.relative_to(path)))

        repo_structure = "\n".join(
            sorted(files_list)
        )
    except Exception as e:
        common.log_warning(f"Falha ao mapear estrutura do repositório: {e}")

    # 🆕 CAPTURA DE CONTEXTO (APP -> INFRA)
    if repo_type == "app":
        stack_info = detect_stack_info(repo_structure, path)
        if stack_info:
            APP_STACK_MEMORY[repo_name] = stack_info
            common.console.print(f"[dim]🧠 Stack Detectada: {stack_info}[/dim]")

    app_context_str = ""
    if APP_STACK_MEMORY:
        app_context_str = "\nCONTEXTO DAS APLICAÇÕES (Stack Detectada):\n" + "\n".join(
            [f"- {k}: {v}" for k, v in APP_STACK_MEMORY.items()]
        )

    # Busca arquivos Terraform
    tf_files = list(path.glob("**/*.tf"))

    issues_count = 0
    if tf_files:
        # Executa TFLint no diretório para pegar contexto de módulo
        tflint_report = tools.get_tflint_report(path)
        # Executa Infracost para contexto de FinOps
        infracost_report = tools.get_infracost_report(path)
        # Executa TFSec para segurança (SAST) - A IA foca em corrigir, não em achar.
        tfsec_report = get_tfsec_report(path)

        for tf_file in tf_files:
            try:
                # Tenta corrigir automaticamente (Auto-Fix) se possível
                # Concatena relatórios externos (Lint + FinOps + Sec)
                full_report = f"{tflint_report}\n{infracost_report}\n{tfsec_report}"
                status = security_auditor.analyze_and_fix_file(
                    tf_file,
                    mode="fix" if mode == "interactive" else "check",
                    repo_structure=repo_structure,
                    external_reports=full_report,
                    app_context=app_context_str,
                )
                if status == "fixed":
                    common.console.print(
                        f"[green]✅ Corrigido automaticamente: {tf_file.name}[/]"
                    )
                elif status == "detected":
                    issues_count += 1
            except Exception as e:
                common.log_warning(f"Falha não-crítica ao auditar {tf_file.name}: {e}")

        if issues_count > 0:
            common.console.print(
                f"\n[bold red]❌ {repo_name}: {issues_count} problemas restantes após tentativa de correção.[/]"
            )
            success = False
        else:
            common.console.print(
                f"\n[bold green]✅ {repo_name}: Infraestrutura validada.[/]"
            )

    # 2. Análise de Alinhamento (App + Pipelines + Scripts)
    common.console.print(
        f"\n[bold magenta]🔍 Verificando alinhamento (App + Pipelines + Scripts)...[/]"
    )

    # Coleta tarefas para execução paralela
    alignment_tasks = []

    # Pipelines e Configurações (YAML) - Abrangente
    for p in list(path.glob("**/*.yml")) + list(path.glob("**/*.yaml")):
        if not is_excluded(p):
            alignment_tasks.append((p, "Configuração YAML"))

    # App Configs
    for f in ["Dockerfile", "requirements.txt", "package.json", "go.mod", "pom.xml", "build.gradle"]:
        for found in path.glob(f"**/{f}"):
            if not is_excluded(found):
                alignment_tasks.append((found, "Dependência de Aplicação"))

    # Scripts / User Data / Python Apps
    for s in (list(path.glob("**/*.sh")) + list(path.glob("**/*.ps1")) + list(path.glob("**/*.py"))):
        if not is_excluded(s) and "test" not in s.name.lower() and "__init__" not in s.name:
            alignment_tasks.append((s, "Script de Automação/App"))

    # Executa análises em paralelo para performance
    alignment_issues = 0
    if alignment_tasks:
        common.console.print(f"[dim]⚡ Executando {len(alignment_tasks)} análises de alinhamento (Sequencial para evitar Rate Limit)...[/dim]")
        # Reduzido de 5 para 1 worker para respeitar cota do Gemini (429 Resource Exhausted)
        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {
                executor.submit(
                    analyze_alignment,
                    f_path,
                    category,
                    repo_name,
                    repo_type,
                    mode,
                    repo_structure,
                    app_context_str,
                    path
                ): f_path for f_path, category in alignment_tasks
            }

            for future in as_completed(futures):
                try:
                    if future.result():
                        alignment_issues += 1
                except Exception as e:
                    common.log_error(f"Falha crítica em tarefa de alinhamento: {e}")
                    alignment_issues += 1

    if alignment_issues > 0:
        success = False

    # 3. Sugestão de Integração (Apenas para Infra)
    if repo_type == "infra":
        # Verifica se já não estamos dentro do projeto (evita sugerir importar a si mesmo)
        root = common.get_project_root()
        should_suggest = True
        try:
            if path.resolve().is_relative_to(root.resolve()):
                should_suggest = False
        except Exception as e:
            common.log_warning(f"Erro ao resolver caminho para sugestão de integração: {e}")

        if should_suggest:
            common.console.print(f"\n[bold cyan]🏗️  Sugestão de Integração (Infra):[/]")
            module_name = repo_name.split("/")[-1].replace("-", "_")

            # Detecta branch atual (default: main)
            current_branch = "main"
            try:
                res = subprocess.run(["git", "branch", "--show-current"], cwd=path, capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    current_branch = res.stdout.strip()
            except Exception as e:
                common.log_warning(f"Falha ao detectar branch git: {e}")

            # Extrai variáveis para preencher o bloco
            detected_vars = extract_terraform_variables(path)

            vars_lines = []
            if detected_vars:
                # Prioriza variáveis obrigatórias no topo
                sorted_vars = sorted(detected_vars.items(), key=lambda item: (not item[1]['required'], item[0]))

                for var_name, info in sorted_vars:
                    if info['required']:
                        vars_lines.append(f'  {var_name} = "" # (Obrigatório)')
                    else:
                        vars_lines.append(f'  # {var_name} = ... # (Opcional - possui default)')

                vars_block = "\n".join(vars_lines)
            else:
                vars_block = "  # Nenhuma variável detectada ou todas possuem defaults implícitos."

            module_block = f"""
module "{module_name}" {{
  source = "git::https://github.com/{repo_name}.git?ref={current_branch}"
{vars_block}
}}
"""
            common.console.print(
                Panel(module_block, title="Terraform Module Block", border_style="blue")
            )
            if (
                mode == "interactive"
                and Prompt.ask(
                    "Deseja adicionar este bloco ao main.tf do projeto?",
                    choices=["s", "n"],
                    default="n",
                )
                == "s"
            ):
                main_tf = common.get_project_root() / "infrastructure" / "main.tf"
                with open(main_tf, "a", encoding="utf-8") as f:
                    f.write(f"\n// Integrado via Git Audit\n{module_block}")
                common.log_success("Módulo adicionado ao main.tf!")

    # 4. Git Push (Devolver ao repositório)
    if (path / ".git").exists():
        common.console.print(f"\n[bold cyan]🔄 Ciclo Git:[/]")
        if (
            mode == "interactive"
            and Prompt.ask(
                f"Deseja devolver o código alinhado para o repositório (Git Push)?",
                choices=["s", "n"],
                default="n",
            )
            == "s"
        ):
            try:
                subprocess.run(["git", "add", "."], cwd=path, check=True)
                # Commit pode falhar se não houver mudanças (não é erro crítico)
                subprocess.run(
                    ["git", "commit", "-m", "refactor: A-PONTE Auto-Fix & Alignment"],
                    cwd=path,
                    check=False,
                )

                # Sincroniza antes de enviar (Evita rejeição por non-fast-forward)
                pull_success = True
                try:
                    current_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, text=True).strip()

                    if current_branch == "HEAD":
                        common.log_warning("Detached HEAD detectado. Ignorando Git Push para evitar criação de branch 'HEAD'.")
                        return success

                    if current_branch:
                        common.console.print(f"[dim]🔄 Sincronizando remoto (git pull --rebase)...[/dim]")

                        # SECURITY FIX: Injeta token em memória também para o pull se a URL estiver mascarada
                        remote_url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=path, text=True).strip()
                        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

                        # Robustez: Injeta token se houver mascaramento OU se for HTTPS sem usuário (CI environment)
                        if "******" in remote_url or ("https://" in remote_url and "@" not in remote_url):
                            if not token:
                                common.log_error("Token GitHub ausente para URL mascarada.")
                                pull_success = False
                            else:
                                encoded_token = urllib.parse.quote(token, safe="")
                                if "******" in remote_url:
                                    auth_url = remote_url.replace("******", encoded_token)
                                else:
                                    parsed = urllib.parse.urlparse(remote_url)
                                    new_netloc = f"x-access-token:{encoded_token}@{parsed.netloc}"
                                    auth_url = parsed._replace(netloc=new_netloc).geturl()
                                subprocess.run(["git", "pull", "--rebase", auth_url, current_branch], cwd=path, check=True, env=git_env)
                        else:
                            subprocess.run(["git", "pull", "--rebase", "origin", current_branch], cwd=path, check=True, env=git_env)
                except subprocess.CalledProcessError:
                    # Se houver conflito, aborta o rebase para não deixar o repo em estado sujo
                    subprocess.run(["git", "rebase", "--abort"], cwd=path, check=False)
                    common.log_warning("Conflito detectado no pull. Abortando push para evitar inconsistência.")
                    pull_success = False

                if not pull_success:
                    return False

                # Tenta push padrão, com fallback para upstream se falhar

                # SECURITY FIX: Se a URL estiver mascarada (******), injeta o token apenas na memória para o push
                remote_url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=path, text=True).strip()
                token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

                if "******" in remote_url or ("https://" in remote_url and "@" not in remote_url):
                    if token:
                        # Reconstrói a URL autenticada temporariamente para este comando
                        encoded_token = urllib.parse.quote(token, safe="")
                        if "******" in remote_url:
                            auth_url = remote_url.replace("******", encoded_token)
                        else:
                            parsed = urllib.parse.urlparse(remote_url)
                            new_netloc = f"x-access-token:{encoded_token}@{parsed.netloc}"
                            auth_url = parsed._replace(netloc=new_netloc).geturl()
                        subprocess.run(["git", "push", auth_url, current_branch], cwd=path, check=True, env=git_env)
                    else:
                        common.log_error("Token não encontrado para realizar push em URL mascarada.")
                        return
                else:
                    subprocess.run(["git", "push", "origin", current_branch], cwd=path, check=True, env=git_env)

                common.log_success("Alterações enviadas com sucesso!")
            except subprocess.CalledProcessError:
                try:
                    # Fallback: Tenta configurar upstream automaticamente
                    current_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, text=True).strip()

                    if current_branch == "HEAD":
                        common.log_warning("Detached HEAD detectado durante fallback. Abortando.")
                        return

                    common.console.print(f"[yellow]⚠️  Push padrão falhou. Tentando configurar upstream para '{current_branch}'...[/]")

                    # SECURITY FIX: Injeta token também no fallback se necessário
                    remote_url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=path, text=True).strip()
                    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
                    if "******" in remote_url or ("https://" in remote_url and "@" not in remote_url):
                        if token:
                            encoded_token = urllib.parse.quote(token, safe="")
                            if "******" in remote_url:
                                auth_url = remote_url.replace("******", encoded_token)
                            else:
                                parsed = urllib.parse.urlparse(remote_url)
                                new_netloc = f"x-access-token:{encoded_token}@{parsed.netloc}"
                                auth_url = parsed._replace(netloc=new_netloc).geturl()
                            subprocess.run(["git", "push", "--set-upstream", auth_url, current_branch], cwd=path, check=True, env=git_env)
                        else:
                            common.log_error("Token não encontrado para configurar upstream em URL mascarada.")
                    else:
                        subprocess.run(["git", "push", "--set-upstream", "origin", current_branch], cwd=path, check=True, env=git_env)

                    common.log_success("Upstream configurado e alterações enviadas!")
                except Exception as e2:
                    common.log_error(f"Falha definitiva no Git Push: {e2}")

    return success


def audit_repo(repo_url, repo_type, temp_dir, mode="interactive"):
    """Clona e audita um repositório remoto."""
    # SECURITY FIX: Prevent Git Argument Injection (Flag Injection)
    if repo_url.startswith("-"):
        common.log_error(f"URL de repositório inválida (Flag Injection detectado): {repo_url}")
        return False

    # Normaliza URL
    if not repo_url.startswith("http") and not repo_url.startswith("git@"):
        full_url = f"https://github.com/{repo_url}.git"
        repo_name = repo_url.rstrip("/").split("/")[-1]
    else:
        full_url = repo_url
        # FIX: Força HTTPS para GitHub para garantir que a injeção de token funcione
        if "github.com" in full_url and full_url.startswith("http://"):
            full_url = full_url.replace("http://", "https://")
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    # AUTENTICAÇÃO ROBUSTA (Token Injection):
    # Previne travamento do script solicitando credenciais no terminal se o token falhar
    git_env = os.environ.copy()
    git_env["GIT_TERMINAL_PROMPT"] = "0"

    # Resolve o problema de "Git no Vácuo" (Docker) injetando o token na URL se disponível.
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

    # FIX: Se tiver token, converte SSH para HTTPS para permitir injeção (Suporte a CI/CD sem chaves SSH)
    if token and full_url.startswith("git@") and "github.com" in full_url:
        full_url = full_url.replace(":", "/").replace("git@", "https://")

    safe_url_for_log = full_url  # URL segura para logs (sem token)

    clean_url = full_url # URL limpa para restore
    # FIX: Uso de urllib para manipulação robusta de URL em vez de string replace frágil
    if token and "github.com" in full_url and "x-access-token" not in full_url:
        try:
            parsed = urllib.parse.urlparse(full_url)
            # Apenas injeta se for HTTPS e não tiver usuário definido (ex: user@host)
            if parsed.scheme == "https" and not parsed.username:
                encoded_token = urllib.parse.quote(token, safe="")
                # Reconstrói a URL injetando as credenciais no netloc
                new_netloc = f"x-access-token:{encoded_token}@{parsed.netloc}"
                full_url = parsed._replace(netloc=new_netloc).geturl()
                safe_url_for_log = full_url.replace(encoded_token, "******")
        except Exception as e:
            common.log_warning(f"Falha ao processar URL para injeção de token: {e}")

    clone_path = Path(temp_dir) / repo_name

    # OTIMIZAÇÃO: Se já existe, tenta atualizar (Fetch + Reset) em vez de clonar do zero
    if clone_path.exists() and (clone_path / ".git").exists():
        common.console.print(f"\n[bold cyan]🔄 Atualizando repositório: {repo_name}...[/]")
        try:
            # Fetch seguro: Usa git -c para injetar a URL com token apenas na memória deste comando
            # Evita gravar o token no .git/config (Risco de vazamento em disco)
            fetch_cmd = ["git"]
            if token and "x-access-token" in full_url:
                fetch_cmd.extend(["-c", f"remote.origin.url={full_url}"])
            fetch_cmd.extend(["fetch", "origin"])

            subprocess.run(fetch_cmd, cwd=clone_path, check=True, stderr=subprocess.PIPE, env=git_env)

            # FIX: Garante que a referência origin/HEAD exista antes do reset (evita erro em repos sem default branch setada)
            subprocess.run(["git", "remote", "set-head", "origin", "-a"], cwd=clone_path, check=False, stderr=subprocess.PIPE, env=git_env)
            subprocess.run(["git", "reset", "--hard", "origin/HEAD"], cwd=clone_path, check=True, stderr=subprocess.PIPE)
            subprocess.run(["git", "clean", "-fdx"], cwd=clone_path, check=True, stderr=subprocess.PIPE)

            return audit_directory(clone_path, repo_name, repo_type, mode=mode)
        except Exception as e:
            common.log_warning(f"Falha ao atualizar cache ({e}). Tentando limpar e reclonar...")
            try:
                # Retry logic for Windows file locks
                for _ in range(3):
                    try:
                        shutil.rmtree(clone_path, onerror=remove_readonly)
                        break
                    except OSError:
                        time.sleep(1)
            except Exception as e_rm:
                common.log_error(f"Não foi possível limpar o cache em {clone_path}: {e_rm}")
                # Tenta mover para lixo para não bloquear a nova clonagem
                try:
                    trash_path = clone_path.with_suffix(f".trash.{datetime.now().timestamp()}")
                    clone_path.rename(trash_path)
                    common.log_warning(f"Cache corrompido movido para {trash_path.name}.")
                except Exception as e_trash:
                    common.log_error(f"Falha crítica ao liberar diretório de cache ({e_trash}). Abortando.")
                    return False

    # Limpeza preventiva: Se o diretório existe mas não é um repo (ex: clone falhou antes), remove.
    if clone_path.exists() and not (clone_path / ".git").exists():
        common.log_warning(f"Caminho {clone_path.name} existe mas não é um repositório Git. Limpando...")
        if clone_path.is_dir():
            shutil.rmtree(clone_path, onerror=remove_readonly)
        else:
            clone_path.unlink()

    common.console.print(f"\n[bold cyan]⬇️  Clonando repositório: {repo_name}...[/]")
    try:
        subprocess.run(
            ["git", "clone", full_url, str(clone_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=git_env
        )
    except FileNotFoundError:
        common.log_error("Git não encontrado no PATH. Instale o git para continuar.")
        return False
    except subprocess.CalledProcessError as e:
        common.log_error(f"Falha ao clonar {safe_url_for_log}.")
        # Sanitiza o erro para garantir que o token não vaze se o git imprimir a URL
        sanitized_stderr = e.stderr.strip().replace(token, "******") if token else e.stderr.strip()
        common.console.print(f"[red]{sanitized_stderr}[/]")
        return False
    finally:
        # SECURITY FIX: Remove token do .git/config immediately após o clone (Success or Failure)
        # Isso impede que o token fique persistido em texto plano no disco (cache)
        if token and "x-access-token" in full_url and clone_path.exists() and (clone_path / ".git").exists():
            # Restaura URL limpa (sem token e sem asterisks)
            restore_url = locals().get("clean_url", safe_url_for_log.replace("******", ""))
            subprocess.run(
                ["git", "remote", "set-url", "origin", restore_url],
                cwd=clone_path,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    # Delega para a função de diretório
    return audit_directory(clone_path, repo_name, repo_type, mode=mode)


def main():
    parser = argparse.ArgumentParser(description="A-PONTE Git AI Auditor")

    # Detecta modo CI/CD para evitar travamento em prompts (ADR-007)
    # Se não houver TTY (ex: execução via Agente), força modo check para evitar hang
    default_mode = "check" if os.getenv("FORCE_NON_INTERACTIVE") == "true" or not sys.stdin.isatty() or not sys.stdout.isatty() else "interactive"

    parser.add_argument(
        "--local", help="Caminho local ou 'project' para auditar repos do projeto"
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "check"],
        default=default_mode,
        help="Modo de execução",
    )
    args = parser.parse_args()

    # Define diretório de cache persistente (Memória de Trabalho da IA)
    cache_dir = common.get_project_root() / ".aponte-versions" / "git_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    common.console.rule("[bold magenta]🐙 A-PONTE Git AI Auditor[/]")
    provider_label = getattr(llm_client, "AI_PROVIDER", "ollama").title()
    common.console.print(
        f"[dim]🧠 Cérebro Ativo: {llm_client.get_active_model()} ({provider_label})[/dim]\n"
    )

    has_failures = False
    # Verifica se foi passado um caminho local via argumento (--local <path>)
    if args.local:
        target = args.local

        # 🆕 Modo Projeto Local: Itera sobre repos vinculados buscando pastas locais
        if target == "project":
            project_name = common.read_context()
            if project_name == "home":
                common.log_error("Modo projeto requer um contexto ativo.")
                return

            repos = get_linked_repos(project_name)
            if not repos:
                common.log_warning(
                    f"Nenhum repositório vinculado ao projeto '{project_name}'."
                )
                return

            common.console.print(
                f"[bold cyan]📂 Auditando repositórios locais do projeto '{project_name}'...[/]"
            )

            root = common.get_project_root()
            for repo_full_name, repo_type in repos:
                repo_short_name = repo_full_name.split("/")[-1]

                # 1. Busca no Isolamento Físico (Novo Padrão)
                isolated_path = root / "projects" / project_name / "repos" / repo_short_name
                # 2. Busca como Irmão (Legacy/Dev)
                sibling_path = root.parent / repo_short_name

                target_path = isolated_path if isolated_path.exists() else (sibling_path if sibling_path.exists() else None)

                if target_path:
                    common.console.print(
                        f"\n[bold]🔹 Repositório: {repo_full_name} ({repo_type})[/]"
                    )
                    if not audit_directory(
                        target_path, repo_short_name, repo_type, mode=args.mode
                    ):
                        has_failures = True
                else:
                    common.console.print(
                        f"\n[bold yellow]⚠️  Repositório local não encontrado em: {isolated_path} ou {sibling_path}[/]"
                    )

                    # Modo Pipeline (Check): Baixa automaticamente para garantir cobertura
                    if args.mode == "check":
                        common.console.print(
                            f"[dim]⬇️  Pipeline: Baixando versão remota para auditoria temporária...[/dim]"
                        )
                        if not audit_repo(repo_full_name, repo_type, cache_dir, mode=args.mode):
                            has_failures = True

                    # Modo Interativo: Pergunta
                    elif (
                        args.mode == "interactive"
                        and Prompt.ask(
                            f"Deseja baixar e auditar a versão remota (Git) de {repo_full_name}?",
                            choices=["s", "n"],
                            default="s",
                        )
                        == "s"
                    ):
                        if not audit_repo(repo_full_name, repo_type, cache_dir, mode=args.mode):
                            has_failures = True

            if has_failures and args.mode == "check":
                sys.exit(1)
            return

        local_path = Path(target)
        if not local_path.exists():
            common.log_error(f"Caminho não encontrado: {local_path}")
            return

        if local_path.is_file():
            common.log_error(f"O alvo da auditoria deve ser um diretório, não um arquivo: {local_path}")
            return

        repo_name = local_path.name
        # Tenta inferir tipo
        repo_type = "infra" if list(local_path.glob("*.tf")) else "app"

        common.console.print(
            f"[bold cyan]📂 Auditando Diretório Local: {local_path} ({repo_type})[/]"
        )
        if not audit_directory(local_path, repo_name, repo_type, mode=args.mode):
            if args.mode == "check":
                sys.exit(1)
        return

    project_name = common.read_context()
    if project_name == "home":
        common.log_error("Você está no contexto 'home'. Selecione um projeto primeiro.")
        return

    repos = get_linked_repos(project_name)
    if not repos:
        common.log_warning(f"Nenhum repositório vinculado ao projeto '{project_name}'.")
        common.console.print(
            "👉 Use a opção [3] Add Repo para vincular os repositórios do projeto."
        )
        return

    common.log_info(
        f"Auditando {len(repos)} repositórios vinculados ao projeto '{project_name}'..."
    )

    for repo, rtype in repos:
        common.console.print(f"\n[bold]🔍 Auditando {repo} ({rtype})...[/]")
        if not audit_repo(repo, rtype, cache_dir, mode=args.mode):
            has_failures = True

    if has_failures and args.mode == "check":
        sys.exit(1)


if __name__ == "__main__":
    main()
