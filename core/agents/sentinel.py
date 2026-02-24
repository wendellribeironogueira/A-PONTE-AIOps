#!/usr/bin/env python3
import sys
import os
import time
import re
import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.lib import aws
from core.services import llm_gateway as llm_client
from core.domain import prompts as system_context

def sanitize_log(text: str) -> str:
    """Remove credenciais e dados sensíveis dos logs antes de processar."""
    # Mascara AWS Access Keys (AKIA/ASIA...)
    text = re.sub(r'(AKIA|ASIA)[A-Z0-9]{16}', '***AWS_KEY***', text)
    # Mascara padrões genéricos de segredos (heuristicamente)
    text = re.sub(r'(?i)(secret|token|password|key)\s*[:=]\s*["\']?([a-zA-Z0-9/+_\-]{20,})["\']?', r'\1: ***SECRET***', text)
    return text

def analyze_threats_cognitively(events, project_name: str):
    """Envia eventos para análise de IA usando o Framework Cognitivo."""
    if not events:
        return

    # Serializa para facilitar a leitura pelo LLM
    events_summary = [
        sanitize_log(f"- {e.get('EventTime')} | {e.get('EventName')} | User: {e.get('Username')} | Source: {e.get('SourceIPAddress')}")
        for e in events
    ]

    prompt = f"""
    {system_context.APONTE_CONTEXT}

    Atue como o Agente Sentinel (Security Daemon) monitorando o projeto: {project_name}.

    FRAMEWORK COGNITIVO (THREAT DETECTION):
    1. **Contextualização:** Analise os logs do CloudTrail abaixo.
    2. **Padrões:** Busque por anomalias (Root Login, Erros de Permissão em massa, Acesso de IPs exóticos).
    3. **Decisão:** Se for atividade normal, responda SAFE. Se for suspeito, explique o risco em 1 frase.

    EVENTOS:
    {chr(10).join(events_summary)}
    """

    try:
        # Timeout curto (30s) para não travar o daemon de segurança
        # PRIVACIDADE: Força execução local (Ollama) para não enviar logs de segurança para a nuvem
        analysis = llm_client.generate(prompt, verbose=False, timeout=30, provider="ollama")
        if analysis and "SAFE" not in analysis:
            common.log_warning(f"🧠 Sentinel AI Insight:\n{analysis}")
    except Exception as e:
        # Falha na IA não deve parar o daemon
        common.log_warning(f"Falha na análise cognitiva do Sentinel: {e}")

def try_acquire_lock(event_id: str) -> bool:
    """Tenta adquirir um lock distribuído para o evento no DynamoDB (Race to Process)."""
    try:
        table = aws.get_session().resource("dynamodb").Table(aws.EVENTS_DEDUP_TABLE)
        # TTL de 24h para limpeza automática
        ttl = int(time.time()) + 86400

        table.put_item(
            Item={"EventID": event_id, "ExpirationTime": ttl},
            ConditionExpression="attribute_not_exists(EventID)"
        )
        return True
    except Exception as e:
        # Se falhar (ex: ConditionCheckFailedException), significa que outro Sentinel já pegou.
        if "ConditionCheckFailedException" in str(e):
            return False
        common.log_error(f"Erro ao adquirir lock no DynamoDB: {e}")
        return False

LAST_DRIFT_CHECKS = {}
DRIFT_CHECK_INTERVAL = 3600  # 1 hora

def check_drift(project_name: str):
    """Verifica drift de infraestrutura periodicamente por projeto (Drift Detection)."""
    global LAST_DRIFT_CHECKS

    # Evita execução em contexto global ou se o intervalo não passou para este projeto específico
    last_check = LAST_DRIFT_CHECKS.get(project_name, 0)
    if project_name == "home" or (time.time() - last_check < DRIFT_CHECK_INTERVAL):
        return

    try:
        root = common.get_project_root()
        
        # Lógica de resolução de caminho (Alinhada com pipeline.py)
        # O projeto 'a-ponte' geralmente mapeia para infrastructure/bootstrap ou infrastructure/
        if project_name == "a-ponte":
            if (root / "infrastructure" / "bootstrap").exists():
                rel_path = "infrastructure/bootstrap"
            elif (root / "infrastructure").exists():
                rel_path = "infrastructure"
            else:
                rel_path = f"projects/{project_name}"
        else:
            rel_path = f"projects/{project_name}"

        project_path = (root / rel_path).resolve()

        # Security: Previne Path Traversal
        if not project_path.is_relative_to(root):
            common.log_error(f"Tentativa de Path Traversal detectada: {project_name}")
            return

        if not project_path.exists():
            # Silencioso se o projeto não existir localmente (pode ser apenas registro no Dynamo)
            return

        # Detecção de Ambiente (Docker vs Host)
        # ADR-028: Preferir execução no Sandbox para garantir caminhos /app/...
        use_docker = False
        try:
            if shutil.which("docker"):
                res = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", "mcp-terraform"],
                    capture_output=True, text=True, check=False
                )
                if res.returncode == 0 and "true" in res.stdout.strip():
                    use_docker = True
        except Exception as e:
            common.log_warning(f"Falha na detecção do Docker (Drift Check): {e}. Usando execução local.")

        if use_docker:
            # Execução via Docker (Sandbox)
            cmd = [
                "docker", "exec",
                "-w", f"/app/{rel_path}",
                "-e", "TF_IN_AUTOMATION=true",
                "-e", "TG_NON_INTERACTIVE=true",
                "-e", f"TF_VAR_project_name={project_name}",
                "mcp-terraform",
                "/usr/local/bin/terragrunt", "plan", "--terragrunt-non-interactive", "-detailed-exitcode", "-lock=false", "-input=false"
            ]
            cwd = None
            env = None
        else:
            # Fallback Local (Host) - Pode falhar se main.tf usar caminhos absolutos /app
            cmd = ["terragrunt", "plan", "--terragrunt-non-interactive", "-detailed-exitcode", "-lock=false", "-input=false"]
            cwd = str(project_path)
            env = os.environ.copy()
            env["TF_VAR_project_name"] = project_name
            env["TF_IN_AUTOMATION"] = "true"
            env["TG_NON_INTERACTIVE"] = "true"
            env["AWS_PAGER"] = ""

        # Executa sem travar o daemon (timeout de segurança)
        # check=False para tratar exit codes manualmente (0=OK, 2=Drift, 1=Erro)
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )

        if result.returncode == 2:
            common.log_error(f"🚨 DRIFT DETECTADO em {project_name}!\n{sanitize_log(result.stdout)[:1000]}...")
        elif result.returncode != 0 and result.returncode != 2:
            # Pega o final do log (tail) onde geralmente está o erro real
            err_log = sanitize_log(result.stderr).strip()
            if not err_log:
                err_log = sanitize_log(result.stdout).strip()

            if result.returncode == 127:
                common.log_warning(f"Falha na verificação de drift (Exit 127): Comando ou Diretório não encontrado.\nVerifique se o caminho '/app/{rel_path}' existe no container e se 'terragrunt' está instalado.\nDetalhes: {err_log}")
            else:
                if len(err_log) > 1000:
                    err_log = f"... [TRUNCATED] ...\n{err_log[-1000:]}"
                common.log_warning(f"Falha na verificação de drift (Exit Code {result.returncode}):\n{err_log}")

        LAST_DRIFT_CHECKS[project_name] = time.time()
    except FileNotFoundError:
        common.log_error("Erro: Binário 'terragrunt' não encontrado no PATH. Drift check ignorado.")
    except PermissionError:
        common.log_error("Erro: Permissão negada ao executar 'terragrunt'. Verifique o bit de execução.")
    except subprocess.TimeoutExpired:
        common.log_error(f"Timeout na verificação de drift ({project_name}). Processo encerrado por segurança.")

    except Exception as e:
        common.log_error(f"Erro ao executar drift check: {e}")

def scan_threats(project_name: str):
    """Verifica CloudTrail por eventos de segurança críticos."""
    try:
        client = aws.get_client("cloudtrail")

        # Busca eventos dos últimos 60 minutos (Aumentado para cobrir incidentes recentes)
        start_time = datetime.now() - timedelta(minutes=60)

        # Lista expandida de eventos críticos
        critical_events = [
            "ConsoleLogin",
            "AuthorizeSecurityGroupIngress",
            "CreateUser",
            "CreateAccessKey",
            "DeleteTrail",
            "StopLogging",
            "RunInstances",       # Detecta EC2 Órfã (Mineração/Backdoor)
            "CreateBucket",       # Detecta Exfiltração de dados
            "CreateFunction2",    # Detecta Lambda Backdoor
            "CreateDBInstance",   # RDS (Banco de Dados)
            "CreateTable",        # DynamoDB
            "CreateTopic",        # SNS
            "CreateQueue",        # SQS
            "CreateLoadBalancer", # ELB
            "CreateVpc"           # VPC (Rede não autorizada)
        ]

        event_list = []
        for evt_name in critical_events:
            res = client.lookup_events(
                LookupAttributes=[{'AttributeKey': 'EventName', 'AttributeValue': evt_name}],
                StartTime=start_time,
                MaxResults=5
            )
            event_list.extend(res.get('Events', []))

        # 1. Análise Heurística (Determinística/Rápida)
        unique_events = []
        for e in event_list:
            # Deduplicação Distribuída: Tenta gravar no DynamoDB
            event_id = e.get('EventId')
            if not try_acquire_lock(event_id):
                continue
            username = e.get('Username')
            if username == 'root':
                common.log_error(f"🚨 ALERTA CRÍTICO [{project_name}]: Login de ROOT detectado em {e['EventTime']}!")

            unique_events.append(e)

        # 2. Análise Cognitiva (IA)
        if unique_events:
            analyze_threats_cognitively(unique_events, project_name)

    except Exception as e:
        # Loga o erro para visibilidade, mas mantém o daemon rodando
        common.log_error(f"Erro no ciclo de monitoramento Sentinel: {e}")

def main():
    common.console.rule("[bold red]🤖 A-PONTE Sentinel Daemon[/]")
    common.console.print("[dim]Monitorando ameaças em background (Ctrl+C para parar)...[/dim]")

    # Tenta iniciar servidor de IA se necessário (Auto-Healing)
    if not llm_client.is_available():
        llm_client.start_server()

    while True:
        try:
            # FIX: Lê o contexto dentro do loop para suportar troca dinâmica de projetos (ADR-027)
            # Se o usuário mudar de projeto via CLI, o Sentinel deve acompanhar.
            project = common.read_context()
            if not project:
                common.log_warning("Contexto do projeto não encontrado. Aguardando...")
                time.sleep(5)
                continue
            
            scan_threats(project)
            check_drift(project)
            time.sleep(60) # Roda a cada minuto
        except KeyboardInterrupt:
            raise # Permite saída limpa via Ctrl+C
        except Exception as e:
            common.log_error(f"Erro crítico no loop do Sentinel: {e}")
            time.sleep(60) # Espera antes de tentar novamente em caso de erro

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        common.console.print("\n[yellow]Sentinel parando...[/]")
