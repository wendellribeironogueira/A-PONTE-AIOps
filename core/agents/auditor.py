#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import shutil
import time
from datetime import datetime
from pathlib import Path

import boto3
from botocore.config import Config
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
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
# Isso permite que o 'infracost auth login' funcione sem precisar duplicar a chave no .env
if "INFRACOST_API_KEY" not in os.environ:
    try:
        creds_path = Path.home() / ".config" / "infracost" / "credentials.yml"
        if creds_path.exists():
            with open(creds_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "api_key" in line and ":" in line:
                        os.environ["INFRACOST_API_KEY"] = line.split(":", 1)[1].strip()
                        break
    except Exception as e:
        if os.getenv("APONTE_DEBUG") == "1":
            print(f"[DEBUG] Falha ao ler credenciais do Infracost: {e}")

# Tenta importar Docker SDK
try:
    import docker
except ImportError:
    docker = None

from core.agents.base import BaseAgent
from core.domain import prompts as system_context
from core.lib.prompts import PromptLoader
from core.lib import aws
from core.lib import toolbelt as tools
from core.lib import utils as common
from core.services import llm_gateway as llm_client
from core.tools import local_coder
from core.services import versioning


class AuditorAgent(BaseAgent):
    """
    Agente responsável por auditoria de segurança (SAST) e correção automática (Auto-Fix).
    """

    def __init__(self):
        super().__init__(
            name="Auditor",
            description="Agente de Auditoria de Segurança e Correção (SAST/AI)",
        )
        self.findings = []  # Acumula achados para relatório estruturado
        self.prompt_loader = PromptLoader()

    def _check_dependencies(self):
        """Verifica se as ferramentas determinísticas estão instaladas e funcionais."""
        # Lista de ferramentas críticas para a orquestração
        tools_map = {
            "terraform": "Infrastructure as Code",
            "terragrunt": "Orquestrador IaC",
            "tflint": "Linter de Terraform",
            "tfsec": "Scanner de Segurança",
            "checkov": "Scanner de Compliance",
            "infracost": "Estimativa de Custos",
            "hadolint": "Linter de Dockerfile",
            "gitleaks": "Detector de Segredos",
            "trivy": "Scanner de Vulnerabilidades",
            "prowler": "Auditoria de Segurança AWS"
        }

        root = common.get_project_root()
        config_path = root / ".tflint.hcl"

        missing = []
        for cmd, desc in tools_map.items():
            # 1. Verifica no Host (Prioridade)
            if shutil.which(cmd):
                continue

            # 2. Verifica no Container MCP (se Docker estiver disponível)
            found_in_docker = False
            tool_configured = True

            if cmd == "tflint" and not config_path.exists():
                tool_configured = False
                desc = desc + " (Sem .tflint.hcl)"

            if cmd == "infracost" and not os.getenv("INFRACOST_API_KEY"):
                tool_configured = False
                desc = desc + " (Sem INFRACOST_API_KEY)"

            if docker:
                try:
                    client = docker.from_env()
                    container = client.containers.get("mcp-terraform")
                    if container.status == "running":
                        res = container.exec_run(f"which {cmd}")
                        if res.exit_code == 0:
                            found_in_docker = True
                except Exception as e:
                    # Não crasha, mas avisa se o debug estiver ativo ou se for erro crítico
                    if "Permission denied" in str(e):
                        self.console.print("[dim red]⚠️  Erro de permissão no Docker socket.[/]")
                    else:
                        self.console.print(f"[dim red]⚠️  Erro Docker Check: {e}[/]")

            if (not shutil.which(cmd) and not found_in_docker) or not tool_configured:
                missing.append(f"{cmd} ({desc})")

        if missing:
            self.console.print(Panel(
                f"[yellow]⚠️  Ferramentas de Auditoria Ausentes:[/yellow]\n" +
                "\n".join([f"- {m}" for m in missing]) +
                "\n\n[dim]A análise será limitada. Instale-as localmente ou inicie o 'aponte infra up'.[/dim]",
                title="Diagnóstico de Dependências",
                border_style="yellow"
            ))

    def _ensure_tflint_config(self):
        """Garante que o .tflint.hcl existe com regras AWS ativas para reduzir alucinações."""
        root = common.get_project_root()
        config_path = root / ".tflint.hcl"

        # Verifica se precisa atualizar (Se não existe ou se está desatualizado/sem regras da casa)
        should_write = True
        if config_path.exists() and config_path.stat().st_size > 0:
            try:
                if "aws_resource_missing_tags" in config_path.read_text(encoding="utf-8"):
                    should_write = False
            except Exception as e:
                self.console.print(f"[dim yellow]⚠️  Falha ao ler .tflint.hcl existente: {e}[/]")

        if should_write:
            self.console.print("[dim]⚙️  Configurando TFLint (AWS Ruleset) para validação robusta...[/dim]")
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

                # Inicialização do Plugin (Best Effort)
                success = False
                if docker:
                    try:
                        client = docker.from_env()
                        # Verifica se o container existe antes de tentar exec
                        try:
                            container = client.containers.get("mcp-terraform")
                            if container.status == "running":
                                # OTIMIZAÇÃO: Verifica se plugins já estão "assados" na imagem para evitar init redundante
                                # O Dockerfile.mcp instala plugins em /root/.tflint.d
                                check_plugins = container.exec_run("ls -A /root/.tflint.d/plugins")
                                if check_plugins.exit_code == 0 and check_plugins.output.strip():
                                    success = True # Plugins existem, skip init
                                else:
                                    container.exec_run("tflint --init", workdir="/app")
                                    success = True
                        except docker.errors.NotFound:
                            pass
                    except Exception as e:
                        self.console.print(f"[dim yellow]⚠️  Falha ao iniciar TFLint no Docker: {e}[/]")

                if not success and shutil.which("tflint"):
                    subprocess.run(["tflint", "--init"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except Exception as e:
                self.log_warning(f"Falha ao configurar TFLint: {e}")

    def _save_audit_event(
        self,
        file_name: str,
        analysis: str,
        action: str = "Detected",
        version_id: str = None,
    ):
        """Salva o evento de auditoria no histórico central."""
        timestamp = datetime.now().isoformat()
        # TTL: 90 dias
        ttl = int(time.time() + (90 * 24 * 60 * 60))
        project = os.getenv("TF_VAR_project_name") or common.read_context()
        if project:
            project = project.lower()

        # 1. Log Local (Redundância/Fallback)
        try:
            log_dir = common.get_project_root() / "logs"
            log_dir.mkdir(exist_ok=True)
            audit_file = log_dir / "security_audit.jsonl"

            local_event = {
                "timestamp": timestamp,
                "project": project,
                "file": file_name,
                "action": action,
                "analysis_snippet": analysis[:200]
            }
            
            # Atomic Write com Lock (Previne corrupção de JSONL em concorrência)
            with open(audit_file, "a", encoding="utf-8") as f:
                if portalocker:
                    portalocker.lock(f, portalocker.LOCK_EX)
                f.write(json.dumps(local_event, ensure_ascii=False) + "\n")
                if portalocker:
                    portalocker.unlock(f)

            # Log Rotation (Eventual Consistency): Verifica APÓS a escrita
            if audit_file.exists() and audit_file.stat().st_size > 5 * 1024 * 1024:
                timestamp_rot = datetime.now().strftime("%Y%m%d-%H%M%S")
                try:
                    audit_file.rename(log_dir / f"security_audit_{timestamp_rot}.jsonl")
                except OSError:
                    pass # Race condition: Outro processo já rotacionou, segue o jogo.
        except Exception as e:
            self.console.print(f"[dim red]⚠️ Falha ao salvar log de auditoria local: {e}[/dim red]")

        # Tenta salvar no DynamoDB
        try:
            retry_config = Config(retries={"max_attempts": 10, "mode": "adaptive"})
            dynamodb = aws.get_session().resource("dynamodb", config=retry_config)
            table = dynamodb.Table(aws.AI_HISTORY_TABLE)
            item = {
                "ProjectName": project,
                "Timestamp": timestamp,
                "ExpirationTime": ttl,
                "ErrorSnippet": f"Security Audit: {file_name}",
                "Analysis": analysis[:500],  # Limita tamanho
                "Author": aws.get_current_user(),
                "Action": action,
            }
            if version_id:
                item["BackupVersionId"] = version_id

            table.put_item(Item=item)
        except Exception as e:
            self.console.print(f"[dim red]⚠️ Falha ao salvar log de auditoria remoto: {e}[/dim red]")

    def analyze_and_fix(
        self,
        file_path: Path,
        mode: str = "interactive",
        repo_structure: str = "",
        external_reports: str = "",
        app_context: str = "",
    ) -> str:
        # FASE 0: Higiene Determinística (Terraform Fmt)
        # Garante que a IA leia código formatado, mesmo se rodar standalone.
        try:
            root = common.get_project_root()

            # OTIMIZAÇÃO: Usa Docker SDK se disponível
            if docker:
                client = docker.from_env()
                container = client.containers.get("mcp-terraform")
                if file_path.is_absolute() and str(file_path).startswith(str(root)):
                    rel_path = file_path.relative_to(root)
                    container_path = f"/app/{rel_path}"
                    container.exec_run(f"terraform fmt {container_path}")
                else:
                    raise ValueError("Arquivo fora do projeto")
            else:
                # Fallback CLI
                subprocess.run(
                    ["docker", "inspect", "mcp-terraform"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if file_path.is_absolute() and str(file_path).startswith(str(root)):
                    rel_path = file_path.relative_to(root)
                    container_path = f"/app/{rel_path}"
                    subprocess.run(
                        [
                            "docker",
                            "exec",
                            "mcp-terraform",
                            "terraform",
                            "fmt",
                            container_path,
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    raise ValueError("Arquivo fora do projeto")
        except Exception as e:
            # Fallback Local
            self.console.print(f"[dim yellow]⚠️  Falha na formatação via Docker (Tentando local): {e}[/]")
            try:
                subprocess.run(
                    ["terraform", "fmt", str(file_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception as e:
                self.console.print(f"[dim yellow]⚠️  Falha ao formatar {file_path.name} (Sintaxe inválida?): {e}[/]")

        # Atomic Read com Lock Compartilhado (SH)
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                if portalocker:
                    portalocker.lock(f, portalocker.LOCK_SH)
                content = f.read()
            finally:
                if portalocker:
                    portalocker.unlock(f)

        # 1. FASE 1: Validação Determinística (IA Tradicional/SAST)
        # Executa ferramentas rápidas antes de acordar o LLM
        self.console.print(
            f"[dim]🔍 Fase 1: Executando scanners estáticos em {file_path.name}...[/dim]"
        )
        sast_report = tools.get_checkov_report(file_path)
        tfsec_report = tools.get_tfsec_report(file_path)
        tflint_report = tools.get_tflint_report(file_path)

        # OTIMIZAÇÃO DE CARGA (Short-Circuit):
        # Se estivermos em modo CI/CD (check) e as ferramentas tradicionais não acharem nada,
        # confiamos nelas e NÃO chamamos o LLM. Isso economiza GPU/CPU e tempo.
        # Em modo interativo, ainda chamamos o LLM para sugestões arquiteturais (Best Practices).
        if mode == "check":
            if not sast_report and not tfsec_report and not tflint_report:
                self.log_success(
                    f"{file_path.name}: Clean (Validado por Checkov/TFSec). Skipping LLM."
                )
                return "safe"

        # --- ORGANIZAÇÃO DE CÉREBROS ---
        cached_content = None
        if "aponte-ai" in llm_client.get_active_model():
            static_context = ""
        else:
            # Otimização: Usa Cache do Gemini se disponível
            audit_provider = os.getenv("APONTE_AUDIT_PROVIDER", "ollama")
            ctx_data = system_context.get_optimized_context(provider=audit_provider)
            
            if "cached_content" in ctx_data:
                cached_content = ctx_data["cached_content"]
                static_context = "" # Contexto está no cache
            else:
                static_context = ctx_data.get("system_instruction", "")

        # Truncate inputs to prevent LLM timeouts (Token Saving)
        repo_structure = (repo_structure[:4000] + "... (truncated)") if len(repo_structure) > 4000 else repo_structure
        sast_report = (sast_report[:3000] + "... (truncated)") if len(sast_report) > 3000 else sast_report
        tfsec_report = (tfsec_report[:3000] + "... (truncated)") if len(tfsec_report) > 3000 else tfsec_report
        tflint_report = (tflint_report[:3000] + "... (truncated)") if len(tflint_report) > 3000 else tflint_report
        content_display = (content[:15000] + "\n... (truncated)") if len(content) > 15000 else content

        security_directive = self.prompt_loader.load("auditor_security_directive")

        prompt = f"""
        {static_context}

        Você é um Especialista em Terraform, Segurança e FinOps.

        DIRETRIZ DE EFICIÊNCIA (TFLINT/TFSEC FIRST):
        1. Analise PRIMEIRO os relatórios de ferramentas estáticas abaixo (TFLint, Checkov).
        2. Se o TFLint apontar um erro (ex: tipo de instância inválido, falta de criptografia), CORRIJA-O pontualmente.
        3. NÃO tente "inventar" melhorias se o código já estiver seguro e validado pelas ferramentas.
        4. Se os relatórios estiverem vazios e o código seguir os padrões (var.project_name), responda APENAS "SAFE". Economize tokens.

        FRAMEWORK COGNITIVO (AUDITORIA):
        Para cada análise, siga este processo mental antes de responder:
        1. **Contextualização:** Identifique o recurso (ex: S3 Bucket) e o ambiente (var.environment).
        2. **Triagem de Risco:** Verifique violações da SECURITY_DIRECTIVE e dos relatórios SAST (Checkov/TFSec).
        3. **Estratégia de Correção:** Escolha a solução mais segura e padronizada (ex: AES256 para S3).
        4. **Validação:** Garanta que a correção mantém a sintaxe HCL válida e usa variáveis do projeto.
        5. **Decisão:** Se seguro, responda SAFE. Se vulnerável, explique o erro.

        ESTRUTURA DE ARQUIVOS DO PROJETO (Visão Periférica):
        {repo_structure}

        {app_context}

        {security_directive}

        Analise o arquivo '{file_path.name}'.
        {sast_report}
        {tfsec_report}
        {tflint_report}
        {external_reports}

        ATENÇÃO: Analise APENAS o código fornecido abaixo.
        REGRA DE OURO (GROUNDING):
        1. Se o relatório SAST (Checkov/TFSec) estiver vazio E você não vir o erro explicitamente no código abaixo, responda "SAFE".
        2. NÃO alucine vulnerabilidades baseadas nos exemplos. Se o código não tem `ingress {{ cidr_blocks = ["0.0.0.0/0"] }}`, NÃO diga que tem.
        3. Se o arquivo for `backend.tf` ou `provider.tf` e não contiver recursos de rede (Security Groups), NÃO mencione SSH ou portas abertas.
        4. Se o arquivo for `provider.tf`, o uso de `region = var.aws_region` é a prática CORRETA. Não sugira alterar para string fixa.
        5. Se o código estiver vazio ou for apenas comentários, responda "SAFE".

        EXEMPLOS DE ANÁLISE (FEW-SHOT):

        Exemplo 1 (Inseguro - Caos):
        Input: resource "aws_security_group_rule" "ssh" {{ type = "ingress" cidr_blocks = ["0.0.0.0/0"] from_port = 22 ... }}
        Response:
        ### Análise
        Detectei uma regra de Security Group permitindo acesso SSH (porta 22) de qualquer lugar (0.0.0.0/0). Isso viola o princípio de Least Privilege e expõe a infraestrutura a ataques de força bruta.

        (O código corrigido será gerado pelo Local Coder)
        ```

        Exemplo 2 (Seguro - Situação Boa):
        Input: provider "aws" {{ region = var.aws_region ... }}
        Response: "SAFE"

        Se os RELATÓRIOS (SAST/LINT/FINOPS) estiverem vazios, você não encontrar erros lógicos graves E o código seguir os padrões de nomenclatura (var.project_name), responda: "SAFE"

        Se houver vulnerabilidades, custos excessivos OU DESVIOS DE PADRÃO:
        1. Priorize corrigir os erros apontados pelos RELATÓRIOS SAST (Checkov/tfsec).
        2. Corrija avisos de Linting (TFLint) se houver (ex: variáveis não usadas, tipos ausentes).
        3. ALINHAMENTO (EC2/ECR/S3): Refatore recursos hardcoded para usar `var.project_name` como prefixo.
           - Ex: bucket "meu-app" -> "${{var.project_name}}-meu-app".
           - 🛑 EXCEÇÃO: Se for `backend.tf`, NÃO toque em strings hardcoded. O Terraform não aceita variáveis no backend.
        4. KMS REMOVAL: O projeto abandonou KMS CMK.
           - Remova recursos `aws_kms_key` e `aws_kms_alias`.
           - Em S3/EBS/RDS, remova `kms_master_key_id` e use criptografia padrão (AES256/AWS Managed).
        5. Se houver RELATÓRIO FINOPS indicando custos altos, sugira otimizações (ex: gp3, t3.micro, spot instances).
        6. Explique o problema de forma TÉCNICA e OBJETIVA. Evite "textão" ou polidez excessiva. Vá direto ao ponto (Causa Raiz -> Solução).
        7. NÃO gere o código corrigido aqui. Apenas explique o que deve ser feito. O Local Coder fará o trabalho pesado.
        8. Se o Checkov reclamar de falta de criptografia ou versionamento, ative-os no código (Use AES256).

        CÓDIGO:
        ```hcl
        {content_display}
        ```

        RESPOSTA OBRIGATÓRIA:

        ### Análise
        [Explicação do problema e da solução recomendada]
        """

        self.console.print(
            f"[dim]🧠 Fase 2: Análise Generativa (LLM) de {file_path.name}...[/dim]"
        )
        try:
            # Enforce local provider by default, but allow override via env var for smarter models
            audit_provider = os.getenv("APONTE_AUDIT_PROVIDER", "ollama")
            response_text = llm_client.generate(prompt, provider=audit_provider, cached_content=cached_content)
        except Exception as e:
            self.log_error(f"Erro ao analisar {file_path.name}: {e}")
            return "error"

        if not response_text:
            self.log_error(f"Falha ao analisar {file_path.name}")
            return "error"

        # 1. Verifica se a IA considerou seguro explicitamente (sem gerar código ou com texto curto)
        # FIX: Validação estrita para evitar falso positivo com "NOT SAFE"
        clean_response = response_text.strip().upper()
        if re.match(r"^SAFE[.!]?$", clean_response) or clean_response.startswith("SAFE\n") or clean_response.startswith("SAFE "):
            self.log_success(f"{file_path.name}: Seguro.")
            # Registra como seguro no relatório
            self.findings.append({
                "severity": "INFO",
                "tool": "A-PONTE AI",
                "title": "Security Check Passed",
                "resource_id": file_path.name,
                "description": "Nenhuma vulnerabilidade detectada pela IA."
            })
            return "safe"

        # Exibe o código original para comparação
        self.console.print(
            Panel(
                Syntax(content, "terraform", theme="monokai", line_numbers=True),
                title=f"📄 Código Original: {file_path.name}",
                border_style="dim",
            )
        )

        self.console.print(
            Panel(
                Markdown(response_text),
                title=f"🚨 Vulnerabilidades em {file_path.name}",
                border_style="red",
            )
        )

        # Registra o problema detectado
        self.findings.append({
            "severity": "HIGH", # Assume alta se a IA reclamou
            "tool": "A-PONTE AI",
            "title": "AI Detected Vulnerability",
            "resource_id": file_path.name,
            "description": response_text[:200] + "..." # Resumo
        })

        if mode == "check":
            self._save_audit_event(
                file_path.name, response_text, action="Detected (CI/CD)"
            )
            return "detected"

        # Geração de Correção via Local Coder (Self-Healing)
        # Passa a análise da IA como instrução para guiar a correção lógica
        code_match = local_coder.fix_code(content, instruction=response_text, file_path=file_path)

        if code_match:
            # Verifica se o código sugerido é idêntico ao original (Falso Positivo / Idempotência)
            original_norm = re.sub(r"\s+", "", content)
            suggested_norm = re.sub(r"\s+", "", code_match)

            if original_norm == suggested_norm:
                # Lógica Corrigida: Se a IA detectou algo (Fase 2) mas não mudou o código, a correção falhou.
                self.console.print(f"[yellow]⚠️  A IA detectou problemas em {file_path.name}, mas a correção automática não surtiu efeito. Requer revisão manual.[/]")
                return "detected"

            # Safety Check para truncamento (Sincronizado com git_auditor)
            if ("..." in code_match and len(code_match.splitlines()) < 5) or \
               (code_match.strip().endswith("...") and len(code_match) < len(content)):
                self.console.print(
                    "[bold red]❌ A IA gerou código com sintaxe inválida. Sugestão descartada por segurança.[/]"
                )
                return "error"

            # FIX: Safety Net (ADR-018) - Valida sintaxe HCL antes de aceitar
            # Garante que a correção não quebre o parser do Terraform
            if not tools.validate_hcl_syntax(code_match):
                self.console.print("[bold red]❌ A IA gerou código com sintaxe inválida (HCL). Sugestão descartada.[/]")
                return "error"

            if (
                Prompt.ask(
                    f"[bold yellow]Deseja aplicar a correção em {file_path.name}?[/]",
                    choices=["s", "n"],
                    default="n",
                )
                == "s"
            ):
                # FIX: Safety Net (ADR-018) - Aborta se o backup falhar
                try:
                    project = common.read_context()
                    version_id = versioning.version_generic_file(
                        file_path, project, reason="Pre-AI-Fix Backup"
                    )
                    self.console.print(f"[dim]Backup versionado criado: ID {version_id}[/dim]")
                except Exception as e:
                    self.console.print(f"[bold red]⛔ Falha crítica ao criar backup: {e}. Operação abortada.[/]")
                    return "error"

                # Aplica a correção
                # Atomic Write com Lock Exclusivo (EX)
                with open(file_path, "w", encoding="utf-8") as f:
                    try:
                        if portalocker:
                            portalocker.lock(f, portalocker.LOCK_EX)
                        f.write(code_match)
                    finally:
                        if portalocker:
                            portalocker.unlock(f)
                self.log_success(f"Correção aplicada em {file_path.name}!")

                self._save_audit_event(
                    file_path.name, response_text, action="Fixed", version_id=version_id
                )
                return "fixed"
            else:
                self._save_audit_event(file_path.name, response_text, action="Ignored")
                self.console.print(
                    "[dim]💡 Dica: Para um ajuste fino ou segunda opinião, use o [bold]Amazon Q[/] (Menu C -> 2).[/dim]"
                )
            return "skipped"

        self._save_audit_event(file_path.name, response_text, action="Detected")
        return "detected"

    def _save_json_report(self):
        """Salva um relatório JSON compatível com o Doctor."""
        try:
            project = os.getenv("TF_VAR_project_name") or common.read_context()
            if not project:
                return

            reports_dir = common.get_project_root() / "logs" / "security_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = reports_dir / f"{project}.json"
            
            report_data = {
                "timestamp": datetime.now().isoformat(),
                "results": self.findings
            }
            report_file.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
        except Exception as e:
            self.log_warning(f"Falha ao salvar relatório JSON: {e}")

    def run(self, mode="interactive"):
        self.console.rule(f"[bold magenta]🕵️ A-PONTE {self.name} Agent (AI)[/]")

        # Garante ferramentas estáticas antes de chamar a IA
        self._ensure_tflint_config()

        # Diagnóstico de Dependências (Sem Mocks)
        self._check_dependencies()

        # Tenta iniciar o servidor se não estiver rodando (Auto-Wake)
        if not llm_client.is_available():
            # Força inicio do Ollama para garantir auditoria local (Privacidade)
            self.console.print(f"[yellow]⏳ Iniciando servidor de IA Local (Ollama) para auditoria privada...[/]")
            if not llm_client.start_server(force=True):
                self.log_warning("Servidor de IA não detectado ou falha ao iniciar.")
                self.console.print(
                    "👉 Certifique-se de que o serviço de IA está configurado e rodando."
                )
                return

        project_root = common.get_project_root()

        # Expande escopo para infrastructure e modules
        scan_dirs = ["infrastructure", "modules"]

        # Inclui o projeto atual na varredura
        try:
            current_project = os.getenv("TF_VAR_project_name") or common.read_context()
            if current_project:
                current_project = current_project.lower()
            if current_project and current_project not in ["home", "a-ponte"]:
                scan_dirs.append(f"projects/{current_project}")
        except Exception as e:
            self.log_warning(f"Falha ao determinar contexto do projeto para varredura: {e}")

        tf_files = []

        for d in scan_dirs:
            target_dir = project_root / d
            if target_dir.exists():
                self.console.print(f"[dim]📂 Mapeando diretório: {d}...[/dim]")
                tf_files.extend(list(target_dir.rglob("*.tf")))

        if not tf_files:
            self.log_warning(
                "Nenhum arquivo .tf encontrado em infrastructure/ ou modules/."
            )
            return

        stats = {"safe": 0, "fixed": 0, "skipped": 0, "detected": 0, "error": 0}

        try:
            for tf_file in tf_files:
                status = self.analyze_and_fix(tf_file, mode=mode)
                stats[status] = stats.get(status, 0) + 1
            
            # Salva relatório final para o Doctor
            self._save_json_report()
        finally:
            llm_client.stop_server()

        # Relatório Final
        self.console.print()
        table = Table(title="📊 Relatório de Auditoria", border_style="blue")
        table.add_column("Status", style="bold")
        table.add_column("Quantidade", justify="right")

        table.add_row("[green]✅ Seguros[/]", str(stats["safe"]))
        table.add_row(
            "[yellow]⚠️  Detectados (Ignorados)[/]",
            str(stats["skipped"] + stats["detected"]),
        )
        table.add_row("[blue]🛠️  Corrigidos[/]", str(stats["fixed"]))
        table.add_row("[red]❌ Erros[/]", str(stats["error"]))

        self.console.print(Panel(table, expand=False))

        if mode == "check":
            if stats["detected"] > 0 or stats["error"] > 0:
                sys.exit(1)


# --- Camada de Compatibilidade (Para git_auditor.py) ---
def analyze_and_fix_file(
    file_path: Path,
    mode: str = "interactive",
    repo_structure: str = "",
    external_reports: str = "",
    app_context: str = "",
) -> str:
    """Wrapper para manter compatibilidade com scripts que chamam esta função diretamente."""
    agent = AuditorAgent()
    return agent.analyze_and_fix(
        file_path, mode, repo_structure, external_reports, app_context
    )


def save_audit_event(
    file_name: str, analysis: str, action: str = "Detected", version_id: str = None
):
    """Wrapper de compatibilidade."""
    agent = AuditorAgent()
    agent._save_audit_event(file_name, analysis, action, version_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A-PONTE Security Auditor (AI)")
    parser.add_argument(
        "--mode",
        choices=["interactive", "check"],
        default="interactive",
        help="Modo de execução",
    )
    args = parser.parse_args()

    agent = AuditorAgent()
    agent.run(mode=args.mode)
