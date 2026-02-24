#!/usr/bin/env python3
import os
import time
import json
import re
from collections import deque
from typing import Optional
from pathlib import Path

from core.domain import prompts as system_context
from core.lib import aws
from core.lib import utils as common
from core.services import llm_gateway as llm_client
from core.services.knowledge import memory


def sanitize_log(text: str) -> str:
    """Remove credenciais e dados sensíveis dos logs antes de processar."""
    # Mascara AWS Access Keys (AKIA/ASIA...)
    text = re.sub(r'(AKIA|ASIA)[A-Z0-9]{16}', '***AWS_KEY***', text)
    # Mascara padrões genéricos de segredos (heuristicamente)
    text = re.sub(r'(?i)(secret|token|password|key)\s*[:=]\s*["\']?([a-zA-Z0-9/+_\-]{20,})["\']?', r'\1: ***SECRET***', text)
    return text

def _scan_log_file(log_file: Path, project_context: str) -> Optional[str]:
    """Helper para escanear um arquivo de log específico."""
    if not log_file.exists():
        return None

    try:
        # errors="replace" evita crash se houver caracteres binários/estranhos no log
        file_size = log_file.stat().st_size
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            # Otimização: Se o log for gigante (>10MB), lê apenas o final para evitar OOM
            if file_size > 10 * 1024 * 1024:
                f.seek(file_size - 10 * 1024 * 1024)
                f.readline() # Descarta linha parcial

            # Lê as últimas 10000 linhas do buffer carregado (Janela maior para loops de erro)
            lines = list(deque(f, maxlen=10000))

        context_marker = f"[{project_context}]".lower()

        # Lista expandida de padrões de erro para robustez (suporta logs estruturados e níveis críticos)
        # (Removida definição duplicada anterior)
        error_patterns = [
            "[ERROR]", "[FATAL]", "[CRITICAL]", "level=error", "level=fatal",
            "Comando falhou", "Vulnerabilidades encontradas", "Failed checks", "Check failed"
        ]

        # Encontra o índice do ÚLTIMO erro
        # Otimização: next() com generator expression é mais eficiente que loop for explícito
        last_error_idx = next(
            (i for i in range(len(lines) - 1, -1, -1)
             if any(p in lines[i] for p in error_patterns) and (project_context == "home" or context_marker in lines[i].lower())),
            -1
        )

        if last_error_idx == -1:
            return None

        # Captura o Stack Trace
        captured_lines = []
        # Limite de segurança para não pegar o arquivo todo se não achar data
        # Aumentado para 100 para capturar stack traces profundos (Java/Terraform)
        max_trace_lines = 100
        # Captura contexto anterior (20 linhas) para erros de resumo e posterior (100 linhas) para stacktrace
        start_idx = max(0, last_error_idx - 20)
        end_idx = min(len(lines), last_error_idx + 100)

        for i in range(start_idx, end_idx):
            line = lines[i]
            # Se não for a primeira linha e começar com data, é um novo log -> para
            # Se já passamos do erro e encontramos um novo timestamp, paramos (novo log)
            if i > last_error_idx and re.match(r"^\d{4}-\d{2}-\d{2}", line):
                break
            captured_lines.append(line)

        raw_log = "".join(captured_lines).strip()
        return sanitize_log(raw_log)
    except Exception as e:
        common.log_error(f"Falha ao ler log para IA: {e}")
        return None

def get_last_error(project_context: str) -> Optional[str]:
    """Lê todos os arquivos de log na pasta logs/ e retorna o último erro encontrado."""
    log_dir = common.get_project_root() / "logs"

    if not log_dir.exists():
        return None

    # Coleta todos os arquivos recursivamente
    candidates = [p for p in log_dir.rglob("*") if p.is_file()]

    # Ordena por modificação (mais recente primeiro) para pegar o erro mais novo
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for log_file in candidates:
        error = _scan_log_file(log_file, project_context)
        if error:
            # Retorna com indicação da fonte para clareza
            rel_path = log_file.relative_to(log_dir)
            return f"[Fonte: logs/{rel_path}]\n{error}"

    return None

def get_repo_structure() -> str:
    """Gera a estrutura de arquivos do projeto para contexto."""
    try:
        root = common.get_project_root()
        excludes = {
            ".git",
            ".terraform",
            ".aponte-versions",
            "node_modules",
            "venv",
            "__pycache__",
            "logs",
            "output",
            ".idea",
            ".vscode",
        }
        files = []

        # Otimização: os.walk permite modificar 'dirs' in-place para evitar recursão em pastas ignoradas
        for dirpath, dirs, filenames in os.walk(root):
            # Remove diretórios excluídos da travessia
            dirs[:] = [d for d in dirs if d not in excludes]

            rel_path = Path(dirpath).relative_to(root)

            for f in filenames:
                if f not in excludes and not f.endswith(".pyc"):
                    files.append(str(rel_path / f))

            if len(files) > 300:  # Limite de contexto para o LLM
                break

        return "\n".join(sorted(files)[:300])
    except Exception as e:
        common.log_warning(f"Falha ao mapear estrutura do repositório: {e}")
        return ""


def analyze_security_report(project_context: str) -> Optional[str]:
    """Analisa o relatório de segurança estruturado (JSON) em vez de raspar logs."""
    try:
        root = common.get_project_root()
        reports_dir = root / "logs" / "security_reports"

        target_file = None

        # Lógica de Seleção de Arquivo (Contexto Home vs Projeto)
        if project_context == "home":
            # Se estiver no contexto global, busca o relatório mais recente de qualquer projeto
            if reports_dir.exists():
                files = list(reports_dir.glob("*.json"))
                if files:
                    target_file = max(files, key=lambda p: p.stat().st_mtime)
        else:
            target_file = reports_dir / f"{project_context}.json"

        if not target_file or not target_file.exists():
            return None

        # Validação Temporal: Avisa se for antigo mas exibe o conteúdo (Melhor UX)
        time_diff = time.time() - target_file.stat().st_mtime
        warning_prefix = ""
        if time_diff > 1800:
            warning_prefix = f"### ⚠️ Aviso: Relatório Antigo ({int(time_diff/60)} min)\n> Este relatório pode não refletir o estado atual da infraestrutura.\n\n---\n\n"

        try:
            data = json.loads(target_file.read_text())
        except json.JSONDecodeError:
            return f"### ❌ Erro de Leitura\n\nO relatório `{target_file.name}` está corrompido (JSON inválido)."

        # Normalização: Se for dict (ex: Checkov summary), tenta extrair a lista de resultados
        if isinstance(data, dict):
            # Checkov Structure: {'results': {'failed_checks': [...]}}
            if "results" in data and isinstance(data["results"], dict):
                data = data["results"].get("failed_checks", [])
            else:
                # Outros formatos
                data = data.get("results", data.get("findings", []))

        # Suporte a Listas (Trivy / Checkov Multi-Suite)
        elif isinstance(data, list):
            flat_data = []
            for item in data:
                if not isinstance(item, dict): continue
                # Trivy (List of Targets)
                if "Vulnerabilities" in item:
                    flat_data.extend(item.get("Vulnerabilities", []))
                # Checkov Multi-Suite
                elif "results" in item and isinstance(item["results"], dict):
                    flat_data.extend(item["results"].get("failed_checks", []))
            if flat_data:
                data = flat_data

        if not data:
            return f"{warning_prefix}### ✅ Segurança Aprovada\n\nO relatório `{target_file.name}` não aponta vulnerabilidades."

        # Filtra achados relevantes (Robustez para Enum str/obj)
        criticals = [f for f in data if 'CRITICAL' in str(f.get('severity', '')).upper()]
        highs = [f for f in data if 'HIGH' in str(f.get('severity', '')).upper()]
        mediums = [f for f in data if 'MEDIUM' in str(f.get('severity', '')).upper()]
        lows = [f for f in data if 'LOW' in str(f.get('severity', '')).upper()]

        total_issues = len(criticals) + len(highs) + len(mediums) + len(lows)

        if total_issues == 0:
            return f"{warning_prefix}### ✅ Segurança Aprovada\n\nO relatório `{target_file.name}` não aponta vulnerabilidades."

        summary = f"{warning_prefix}### 🛡️ Relatório de Segurança (Centralizado)\n"
        if project_context == "home":
             summary += f"**Fonte:** `{target_file.name}` (Último Scan)\n\n"

        summary += f"Total de Vulnerabilidades: **{total_issues}**\n"
        summary += f"🔴 **{len(criticals)} Críticas** | 🟠 **{len(highs)} Altas** | 🟡 **{len(mediums)} Médias** | 🔵 **{len(lows)} Baixas**\n\n"

        # Prioriza exibição: Critical > High > Medium
        display_list = criticals + highs + mediums
        if len(display_list) < 5:
            display_list.extend(lows)

        for f in display_list[:5]:
            severity_icon = "🔴" if "CRITICAL" in str(f.get('severity')).upper() else "🟠" if "HIGH" in str(f.get('severity')).upper() else "🟡"
            summary += f"- {severity_icon} **[{f.get('tool')}] {f.get('title')}**\n"
            summary += f"  Arquivo: `{f.get('resource_id')}`\n"
            summary += f"  *Correção:* {f.get('description')}\n\n"

        if len(display_list) > 5:
            summary += f"\n... e mais {len(display_list) - 5} problemas."

        summary += f"\n\nConsulte o relatório completo em: `{target_file}`"
        return summary

    except Exception as e:
        common.log_warning(f"Erro ao ler relatório de segurança: {e}")
        return None


def analyze_known_errors(error_msg: str, project_context: str) -> Optional[str]:
    """Análise determinística de erros conhecidos para resposta rápida (Heurística)."""

    # Caso 3: Módulo não encontrado
    if (
        "Unreadable module directory" in error_msg
        and "no such file or directory" in error_msg
    ):
        module_path_match = re.search(r"lstat (.*?): no such", error_msg)
        module_path = (
            module_path_match.group(1) if module_path_match else "desconhecido"
        )

        calling_file_match = re.search(r"at (.*?):\d+", error_msg)
        calling_file = (
            calling_file_match.group(1) if calling_file_match else "desconhecido"
        )

        return f"""
### 🩺 Diagnóstico Determinístico (Módulo Não Encontrado)

**Identificado:** Erro `Unreadable module directory`. O Terraform não conseguiu encontrar um módulo referenciado.

**Análise do Engenheiro:**
O arquivo `{calling_file}` está tentando carregar um módulo do caminho `{module_path}`, mas este diretório ou link simbólico não existe.

Isso geralmente acontece quando um módulo é renomeado ou movido, mas a referência (`source = "..."`) no arquivo que o chama não é atualizada. Por exemplo, o módulo pode ter sido renomeado de `../modules/identity` para `../modules/iam`.

**Solução (Plano de Ação):**
1.  Abra o arquivo `{calling_file}`.
2.  Localize o bloco de módulo que aponta para `{module_path}` e corrija o parâmetro `source` para o caminho correto.
"""

    # Caso 1: Tabela de Lock do DynamoDB inexistente (Bootstrap falhou)
    if "ResourceNotFoundException" in error_msg and "DynamoDB" in error_msg:
        return f"""
### 🩺 Diagnóstico Determinístico (Falha no Backend Compartilhado - DynamoDB)

**Identificado:** A Tabela de Lock Global não foi encontrada ou é inacessível (`ResourceNotFoundException`).

**Análise do Engenheiro:**
O Terraform falhou ao tentar adquirir o State Lock. Conforme o ADR-009, utilizamos uma tabela DynamoDB centralizada.

**Causas Prováveis:**
1. **Bootstrap Incompleto:** A tabela de lock global nunca foi criada.
2. **Permissões:** A Role atual não tem permissão `dynamodb:PutItem` na tabela compartilhada.

**Por que o Terragrunt não resolveu?**
O erro confirma que o **Terragrunt não foi invocado**. O sistema tentou rodar `terraform init` diretamente, perdendo a camada de orquestração.

**Solução (Plano de Ação):**
Execute o bootstrap usando o orquestrador correto (CLI + Terragrunt). O comando abaixo irá forçar o Terragrunt a criar a tabela de lock automaticamente:

```bash
aponte deploy core
```
"""

    # Caso 2: Bucket S3 de Estado inexistente (Bootstrap Paradox - Parte 2)
    if (
        "S3 bucket" in error_msg
        and "does not exist" in error_msg
        and "tfstate" in error_msg
    ):
        bucket_name_match = re.search(r'S3 bucket "(.*?)" does not exist', error_msg)
        bucket_name = (
            bucket_name_match.group(1) if bucket_name_match else "desconhecido"
        )

        iam_diagnosis = """
    - s3:CreateBucket
    - s3:PutBucketVersioning
    - s3:PutBucketTagging
    - s3:PutEncryptionConfiguration
    - dynamodb:CreateTable
    - dynamodb:DescribeTable
    - dynamodb:TagResource
        """
        return f"""
### 🩺 Diagnóstico Determinístico (Bootstrap Paradox - S3)

**Identificado:** O Bucket S3 de estado remoto `{bucket_name}` não existe (`NoSuchBucket`).

**Análise do Engenheiro:**
Este é o problema clássico do "Ovo e a Galinha". O Terragrunt foi projetado para resolver isso criando o bucket automaticamente, mas algo está o impedindo. As causas mais comuns são:

1.  **Permissões na AWS (Causa Mais Provável):** As credenciais AWS que você está usando (seja usuário IAM ou role federada via OIDC) não têm permissão para criar e configurar o bucket S3 e a tabela DynamoDB. O Terragrunt falha silenciosamente e o Terraform falha em seguida.
2.  **Configuração do Terragrunt:** O parâmetro `disable_bucket_update = true` no `root.hcl` pode estar ativo.
3.  **Execução Direta:** O comando `terraform init` foi executado diretamente, ignorando a camada de orquestração do Terragrunt.

**Por que o Terragrunt não resolveu?**
Dado que a orquestração da CLI está correta, a causa mais provável é a falta de **permissões de IAM**.

**Solução (Plano de Ação):**
1.  **Verifique as Permissões de IAM:** Garanta que sua role/usuário possui, no mínimo, as seguintes permissões. Esta é a causa mais comum de falha silenciosa no bootstrap.
    {iam_diagnosis}

2.  **Verifique a Configuração:** Garanta que `disable_bucket_update = false` no seu arquivo `root.hcl`. (Sua configuração atual já está correta).
3.  **Execute o Bootstrap:** Após validar as permissões, execute o comando de bootstrap novamente:

```bash
aponte deploy core
```
"""

    return None


def get_recent_audit_activity(project_context: str, limit: int = 10) -> str:
    """Recupera as últimas ações dos agentes para contexto (Causa e Efeito)."""
    log_file = common.get_project_root() / "logs" / "agent_audit.jsonl"
    if not log_file.exists():
        return ""

    activity = []
    skipped_corrupt = 0
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # Lê as últimas 100 linhas para filtrar
            lines = list(deque(f, maxlen=100))

        for line in reversed(lines):
            try:
                event = json.loads(line)
                # Filtra por projeto se não for 'home'
                if project_context != "home" and event.get("project") != project_context:
                    continue

                ts = event.get("iso_time", "")
                if "T" in ts:
                    ts = ts.split("T")[1].split(".")[0].split("+")[0]

                status = event.get("status", "UNKNOWN")
                icon = "✅" if status == "SUCCESS" else "❌"

                entry = f"- [{ts}] {icon} {event.get('agent')}: {event.get('command')}"
                if status != "SUCCESS":
                    preview = str(event.get("output_preview", ""))
                    if preview:
                        entry += f"\n  └── Output: {preview[:150]}..."

                activity.append(entry)
                if len(activity) >= limit:
                    break
            except json.JSONDecodeError:
                skipped_corrupt += 1
                continue
    except Exception as e:
        common.log_warning(f"Falha ao ler histórico de auditoria: {e}")
        return ""

    if skipped_corrupt > 0:
        common.log_warning(f"Ignoradas {skipped_corrupt} linhas corrompidas no log de auditoria.")

    if not activity:
        return ""

    return "HISTÓRICO RECENTE DE AGENTES (Contexto Operacional):\n" + "\n".join(activity)


def get_security_history(project_context: str, limit: int = 5) -> str:
    """
    Recupera o histórico de auditoria do DynamoDB (Recurso Customizado/DefectDojo Replacement).
    Lê da tabela definida em aws.AI_HISTORY_TABLE.
    """
    try:
        # Evita erro se a lib aws não tiver a constante definida (Retrocompatibilidade)
        if not hasattr(aws, "AI_HISTORY_TABLE"):
            return ""

        session = aws.get_session()
        dynamodb = session.resource("dynamodb")
        table = dynamodb.Table(aws.AI_HISTORY_TABLE)

        # Import local para evitar dependência global se boto3 não estiver no topo
        from boto3.dynamodb.conditions import Key

        # Query otimizada usando PK (ProjectName)
        response = table.query(
            KeyConditionExpression=Key('ProjectName').eq(project_context),
            Limit=limit,
            ScanIndexForward=False # DESC (Mais recentes primeiro)
        )

        items = response.get('Items', [])
        if not items:
            return ""

        history = ["HISTÓRICO DE SEGURANÇA (DynamoDB):"]
        for item in items:
            ts = item.get('Timestamp', '').split('T')[0]
            action = item.get('Action', 'Info')
            snippet = item.get('ErrorSnippet', '')
            history.append(f"- [{ts}] {action}: {snippet}")

        return "\n".join(history)
    except Exception as e:
        common.log_warning(f"Falha ao ler histórico de segurança (DynamoDB): {e}")
        return ""


def ask_ollama(error_msg: str, project_context: str, silent: bool = False):
    """Envia o erro para o LLM local e solicita correção."""
    repo_structure = get_repo_structure()
    docs_context = system_context.load_docs_context()

    security_email = (
        os.getenv("SECURITY_EMAIL")
        or os.getenv("TF_VAR_security_email")
        or "security@aponte.platform"
    )

    # RAG Lite: Recupera experiências passadas do Cérebro Compartilhado
    memory_context = memory.fetch_similar_history(error_msg)

    # Contexto de Auditoria (O que aconteceu antes do erro?)
    audit_context = get_recent_audit_activity(project_context)

    # Contexto de Segurança (DynamoDB - Custom Resource)
    security_context = get_security_history(project_context)

    prompt = f"""
    {system_context.APONTE_CONTEXT}

    CONTACTO DE SEGURANÇA: {security_email}

    {docs_context}

    {memory_context}

    {audit_context}

    {security_context}

    ESTRUTURA DE ARQUIVOS DO PROJETO (Visão Periférica):
    {repo_structure}

    Atue como um Engenheiro SRE Senior especialista em AWS e Terraform para uma plataforma multi-tenant.
    O erro abaixo ocorreu no contexto do projeto '{project_context}'.

    RESTRIÇÃO: O ambiente é 100% AWS. Não mencione Azure ou GCP.
    DIRETRIZ: Use os ADRs e o Guia de Troubleshooting acima para sugerir soluções compatíveis com a arquitetura (ex: Prefira SSM a SSH, use Terragrunt).

    Analise o seguinte erro de log e forneça:
    1. A causa provável.
    2. O comando ou correção exata para resolver, considerando o projeto '{project_context}'.
    3. ANÁLISE DE RISCO: Verifique se este erro indica que algum recurso está sendo criado sem o prefixo do projeto (risco de recurso órfão ou conflito de nome global).
    4. PERMISSÕES: Se o erro for 'AccessDenied' ou relacionado a 'PermissionsBoundary', verifique se é um caso legítimo para sugerir o uso do comando de emergência: 'aponte break-glass enable'.

    ERRO:
    {error_msg}

    Responda em Markdown.
    Seja conciso e técnico.
    IMPORTANTE: Responda sempre em Português do Brasil (PT-BR).
    """

    if not silent:
        common.console.print(
            f"[bold cyan]🤖 Consultando {llm_client.DEFAULT_MODEL} localmente (Contexto: {project_context})...[/]"
        )

    # Usa o cliente centralizado
    # verbose=False para evitar mensagem duplicada do gateway, já que o doctor imprime sua própria mensagem com contexto.
    try:
        return llm_client.generate(prompt, verbose=False)
    except Exception as e:
        common.log_warning(f"Falha ao consultar IA para diagnóstico: {e}")
        return None


def run_silent_diagnosis(project_context: str):
    """Executa o diagnóstico em modo silencioso (para uso em Dashboards/Background)."""
    error = get_last_error(project_context)
    if not error:
        return None

    # 1. Tenta análise determinística (Heurística)
    analysis = analyze_known_errors(error, project_context)

    # Verifica se o Ollama está online antes de tentar
    if not analysis and not llm_client.is_available():
        return None

    if not analysis:
        analysis = ask_ollama(error, project_context, silent=True)

    if analysis:
        memory.save_diagnosis(project_context, error, analysis)
        return analysis
    return None


def main():
    common.console.rule("[bold magenta]🧠 A-PONTE AI Doctor[/]")

    # Diagnóstico de Runtime IA (Validação de Migração)
    model_display = llm_client.get_display_name()
    common.console.print(f"[dim]Modelo Ativo: [bold]{model_display}[/][/dim]")

    project_context = os.getenv("TF_VAR_project_name") or common.read_context()
    if not project_context:
        project_context = "home"

    if project_context:
        project_context = project_context.lower()

    # AUTO-FIX: Se o contexto for 'home', tenta inferir pelo diretório atual
    if project_context == "home":
        try:
            cwd = Path.cwd().resolve()
            root = common.get_project_root().resolve()

            # Tenta inferir projeto tenant (ex: projects/my-app)
            projects_dir = root / "projects"
            if str(cwd).startswith(str(projects_dir)):
                rel_path = cwd.relative_to(projects_dir)
                if rel_path.parts:
                    inferred = rel_path.parts[0]
                    common.console.print(f"[dim]Contexto inferido automaticamente: [bold]{inferred}[/][/dim]")
                    project_context = inferred

            # Tenta inferir projeto core (a-ponte)
            elif str(cwd).startswith(str(root / "infrastructure")):
                inferred = "a-ponte"
                common.console.print(f"[dim]Contexto inferido automaticamente: [bold]{inferred}[/][/dim]")
                project_context = inferred

        except Exception as e:
            common.console.print(f"[dim yellow]⚠️  Falha na inferência automática de contexto: {e}[/]")

    if project_context == "home":
        common.console.print(
            "[yellow]ℹ️  Contexto 'home' detectado. O diagnóstico será executado em modo global (System Logs).[/]"
        )

    # 1. Prioridade: Verifica Relatórios de Segurança (SSOT)
    # Se houve um scan recente que falhou, isso é mais relevante que logs genéricos.
    security_diagnosis = analyze_security_report(project_context)
    if security_diagnosis:
        from rich.markdown import Markdown
        from rich.panel import Panel

        is_safe = "Segurança Aprovada" in security_diagnosis
        common.console.print(
            Panel(
                Markdown(security_diagnosis),
                title=f"🛡️ Diagnóstico de Segurança (Projeto: {project_context})",
                border_style="green" if is_safe else "red",
            )
        )

    error = get_last_error(project_context)
    if not error and not security_diagnosis:
        common.console.print(
            f"[yellow]⚠️  O Doctor não encontrou logs de erro ou relatórios de segurança recentes para '{project_context}'.[/]\n"
        )

        # Diagnóstico de Arquivos Existentes (Transparência)
        reports_dir = common.get_project_root() / "logs" / "security_reports"
        if reports_dir.exists():
            files = list(reports_dir.glob("*.json"))
            if files:
                common.console.print(f"[dim]Relatórios disponíveis (mas antigos ou de outros projetos):[/dim]")
                for f in files[:5]:
                    common.console.print(f" - {f.name} ({time.ctime(f.stat().st_mtime)})")
            else:
                common.console.print("[dim]Nenhum relatório encontrado em logs/security_reports/.[/dim]")

        common.console.print("\n[bold]Diagnóstico:[/bold] A ferramenta executada anteriormente (ex: 'aponte security checkov') provavelmente não salvou o relatório em disco.")
        common.console.print("[bold]Solução:[/bold] Execute [cyan]aponte audit[/] ou [cyan]aponte ops pipeline[/] para gerar relatórios persistentes que o Doctor possa ler.")
        return

    # Se não houver erro operacional (apenas avisos de segurança), encerra aqui
    if not error:
        if security_diagnosis and "Segurança Aprovada" in security_diagnosis:
            common.console.print(
                Panel(
                    "✅ [bold green]Sistema Saudável:[/bold green] Nenhum erro operacional ou de segurança detectado.",
                    border_style="green"
                ))
        return

    common.console.print(
        f"[bold red]Erro Identificado (Contexto: {project_context}):[/bold red]\n{error}\n"
    )

    # 1. Tenta análise determinística
    analysis = analyze_known_errors(error, project_context)

    # 2. Se não houver match, pergunta ao Ollama
    if not analysis:
        analysis = ask_ollama(error, project_context)

    if analysis is None:
        common.console.print(
            f"[yellow]⚠️  Ollama não detectado em {llm_client.OLLAMA_URL}[/yellow]"
        )
        common.console.print("👉 Para ativar a IA Generativa gratuita:")
        common.console.print("   1. Baixe em: https://ollama.com")
        common.console.print(
            f"   2. No terminal, rode: ollama run {llm_client.DEFAULT_MODEL}"
        )
    else:
        from rich.markdown import Markdown
        from rich.panel import Panel

        # 1. Salva o resultado no DynamoDB
        memory.save_diagnosis(project_context, error, analysis)

        # 2. Exibe na tela
        common.console.print(
            Panel(
                Markdown(analysis),
                title=f"💡 Diagnóstico da IA (Projeto: {project_context})",
                border_style="green",
            )
        )


if __name__ == "__main__":
    main()
