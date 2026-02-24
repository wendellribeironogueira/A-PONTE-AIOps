#!/usr/bin/env python3
import json
import os
import platform
import re
import logging
from logging.handlers import RotatingFileHandler
import shlex
import traceback
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.tree import Tree
from langchain_core.messages import HumanMessage, AIMessage

# Setup paths (Robustez para execução direta)
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.agents.base import BaseAgent
from core.lib import aws
from core.lib import toolbelt as tools
from core.lib import utils as common
from core.lib.reflex import ReflexEngine
from core.lib.mcp_manager import ToolManager
from core.lib.parser import ResponseParser
from core.services import llm_gateway as llm_client

class ArchitectAgent(BaseAgent):
    """
    Agente Inteligente responsável pela interação e orquestração.
    Atua como o "Cliente/Bridge" no padrão MCP, conectando o modelo (Ollama)
    aos servidores de ferramentas e executando as ações solicitadas.
    """

    def __init__(self, initial_input=None):
        super().__init__(
            name="Architect", description="Agente Arquiteto Virtual (Chat)"
        )
        self.history = []
        self.user_context_block = ""
        self.context_cache = {} # OTIMIZAÇÃO: Cache estruturado para evitar regex repetitivo
        self.context_confirmed = False
        self.initial_input = initial_input
        self.session_id = str(uuid.uuid4()) # Identificador único da sessão para Checkpointing (Garbage Collection otimizado)

        # Componentes desacoplados (v3.0 Maestro Architecture)
        self.reflex_engine = ReflexEngine()
        self.tool_manager = ToolManager(self.console)
        self.parser = ResponseParser() # Middleware de parsing (v3.0)

        # Initialize Graph Architect (Phase 3)
        from core.agents.graph_architect import GraphArchitect

        # Define path for durable checkpointing
        db_path = common.get_project_root() / "data" / "checkpoints.sqlite"

        self.graph_architect = GraphArchitect(
            tool_manager=self.tool_manager,
            context_resolver=self._get_context_variable,
            audit_logger=self._log_audit_event,
            status_callback=lambda msg: None, # Placeholder inicial, atualizado no run()
            db_path=db_path
        )

        self._setup_audit_logger()
        self.dynamodb_table = None # OTIMIZAÇÃO: Conexão persistente (Lazy Loading)
        self._aws_identity_cache = None # Cache para evitar chamadas STS repetidas

        # Pool de threads para operações de I/O não bloqueantes (Logs, Métricas)
        self._io_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ArchitectIO")

        self.last_generated_code = ""  # Memória de curto prazo para o código gerado
        self.last_generated_filename = None # Rastreia se o código foi gerado para um arquivo específico

        # Eager Loading para Ollama (Local-First Strategy)
        if llm_client.AI_PROVIDER == "ollama":
            # OTIMIZAÇÃO: Desativado Eager Mode para reduzir carga no contexto (Lentidão/Burrice)
            # O modelo 1.5B sofre com muitas ferramentas. Vamos usar carregamento sob demanda via 'load_extension'.
            pass

    def cleanup(self):
        """Encerra todos os processos MCP iniciados."""
        self.tool_manager.cleanup()
        if hasattr(self, "graph_architect"):
            self.graph_architect.cleanup()
        self._io_pool.shutdown(wait=False)

    def _setup_audit_logger(self):
        """Configura o logger de auditoria usando padrões da biblioteca logging."""
        log_dir = common.get_project_root() / "logs"
        log_dir.mkdir(exist_ok=True)
        audit_file = log_dir / "agent_audit.jsonl"

        self.audit_logger = logging.getLogger("agent_audit")
        self.audit_logger.setLevel(logging.INFO)
        self.audit_logger.propagate = False

        if not self.audit_logger.handlers:
            handler = RotatingFileHandler(audit_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.audit_logger.addHandler(handler)

    def _detect_aws_identity(self):
        """Detecta Região e Conta AWS usando credenciais ativas (CLI/Boto3)."""
        # Cache para evitar latência de rede em chamadas subsequentes
        if self._aws_identity_cache:
            return self._aws_identity_cache

        region = os.getenv("AWS_REGION")
        account = os.getenv("TF_VAR_account_id")

        # Se já estiver definido no env, confia (performance)
        if region and account:
            return region, account

        try:
            # Usa a sessão do boto3 configurada no ambiente (profile/credentials)
            session = aws.get_session()

            if not region:
                region = session.region_name

            if not account:
                # Chamada leve ao STS para pegar ID da conta
                sts = session.client("sts")
                account = sts.get_caller_identity()["Account"]

            # FIX: Propaga credenciais explícitas para subprocessos (MCP)
            # Isso resolve o caso onde o boto3 resolve credenciais (ex: SSO/Profile)
            # mas o subprocesso da ferramenta não consegue resolver sozinho.
            creds = session.get_credentials()
            if creds:
                frozen = creds.get_frozen_credentials()
                if frozen:
                    os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
                    os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
                    if frozen.token:
                        os.environ["AWS_SESSION_TOKEN"] = frozen.token

            if session.profile_name and session.profile_name != "default":
                os.environ["AWS_PROFILE"] = session.profile_name

        except Exception as e:
            # REALIDADE: Se falhar, não finja que está na sa-east-1. Avise o usuário.
            self.console.print(f"[dim yellow]⚠️  AWS Identity Check falhou: {str(e)[:100]}... (Modo Offline/Desconectado)[/]")

        final_region = region or "unknown-region"
        final_account = account or "unknown"

        # FIX: Exporta para o ambiente para que as ferramentas (MCP/Subprocess) herdem o contexto correto
        os.environ["AWS_REGION"] = final_region

        self._aws_identity_cache = (final_region, final_account)
        return final_region, final_account

    def _preload_context(self):
        """Carrega contexto existente (Env/Disk) para evitar perguntas redundantes."""
        try:
            project = os.getenv("TF_VAR_project_name") or common.read_context()
            if project and project != "home":
                env = os.getenv("TF_VAR_environment", "dev")
                app = os.getenv("TF_VAR_app_name", "")
                resource = os.getenv("TF_VAR_resource_name", "")
                region, account = self._detect_aws_identity()

                self.user_context_block = f"""
CONTEXTO IMUTÁVEL DO PROJETO (DETECTADO):
- var.project_name = "{project}"
- var.environment = "{env}"
- var.app_name = "{app}"
- var.resource_name = "{resource}"
- var.aws_region = "{region}"
- var.account_id = "{account}"
"""
                # Se um projeto é detectado (não é 'home'), o contexto é considerado confirmado.
                # Isso muda o agente do modo 'Discovery' para o modo 'Architect'.
                self._parse_context_to_cache()
                self.context_confirmed = True
        except Exception as e:
            self.console.print(f"[dim yellow]⚠️  Falha ao pré-carregar contexto: {e}[/]")

    def _parse_context_to_cache(self):
        """Converte o bloco de texto em dicionário para acesso O(1)."""
        if self.user_context_block:
            matches = re.findall(r'var\.(\w+)\s*=\s*"([^"]+)"', self.user_context_block)
            self.context_cache.update(dict(matches))

    def _get_context_variable(self, var_name):
        """Extrai valor de variável do bloco de contexto do usuário."""
        # Prioridade 1: Contexto explícito da sessão de chat (User Context Block)
        if var_name in self.context_cache:
            return self.context_cache[var_name]

        # Fallback: Se não estiver no cache, tenta regex (caso de atualização manual sem refresh do cache)
        if self.user_context_block:
            match = re.search(rf'var\.{var_name}\s*=\s*"([^"]+)"', self.user_context_block)
            if match:
                self.context_cache[var_name] = match.group(1)
                return match.group(1)

        # Prioridade 2: Fallback para o contexto do sistema (Disk/Env)
        # Isso permite que comandos funcionem mesmo antes do "ritual" de contexto
        env_val = os.getenv(f"TF_VAR_{var_name}")
        if env_val:
            return env_val

        if var_name == "project_name":
            return common.read_context()

        return None

    def _log_audit_event(self, tool_name, command, output, status="SUCCESS"):
        """
        AUDITORIA (Production Grade): Registra execução de ferramentas em formato estruturado (JSONL).
        Essencial para compliance, post-mortem e ingestão por SIEM.
        """
        # 1. Log Local (File)
        user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
        event = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "agent": "Architect",
            "user": user,
            "project": self._get_context_variable("project_name") or "unknown",
            "tool": tool_name,
            "command": command,
            "status": status,
            "output_preview": output if output else ""
        }

        try:
            self.audit_logger.info(json.dumps(event, ensure_ascii=False))
        except Exception as e:
            self.console.print(f"[dim red]⚠️ Falha no Audit Log: {e}[/dim red]")

        # 2. Log Remoto (DynamoDB - Imutável)
        # OTIMIZAÇÃO: Executa em background para não bloquear a UI com latência de rede
        def _remote_log_worker():
            try:
                timestamp_iso = datetime.now().isoformat()
                project = self._get_context_variable("project_name") or "unknown"

                # Reutiliza a tabela de histórico de IA para centralizar auditoria
                if not self.dynamodb_table:
                    # OTIMIZAÇÃO: Reutiliza a sessão/resource para evitar overhead de conexão a cada log
                    self.dynamodb_table = aws.get_session().resource("dynamodb").Table(aws.AI_HISTORY_TABLE)

                item = {
                    "ProjectName": project,
                    "Timestamp": timestamp_iso,
                    "ErrorSnippet": f"Tool Exec: {tool_name}", # Reusing schema fields
                    "Analysis": f"Command: {command}\nStatus: {status}\nOutput: {output[:500]}",
                    "Author": aws.get_current_user(),
                    "Action": "AgentToolExecution",
                }
                self.dynamodb_table.put_item(Item=item)
            except Exception:
                pass # Falha silenciosa em background para não poluir a UI

        self._io_pool.submit(_remote_log_worker)

    def _save_session_memory(self):
        """Salva a conversa atual na Base de Conhecimento para treinamento futuro."""
        if not self.history:
            return

        timestamp = int(time.time())
        root = common.get_project_root()
        # Define o diretório de memória de chat
        memory_dir = root / ".aponte" / "chat_sessions"
        memory_dir.mkdir(parents=True, exist_ok=True)

        filename = memory_dir / f"session_{timestamp}.md"

        content = ["# Chat Session Memory", f"Date: {time.ctime()}", ""]
        for interaction in self.history:
            content.append(f"## User\n{interaction['u']}\n")
            content.append(f"## AI\n{interaction['a']}\n")
            content.append("---\n")

        filename.write_text("\n".join(content), encoding="utf-8")
        self.console.print(
            f"[dim]💾 Memória da sessão salva em: .aponte/chat_sessions/{filename.name}[/dim]"
        )

        # Rotação de Logs: Mantém apenas as últimas 20 sessões para evitar poluição do cérebro
        try:
            sessions = sorted(memory_dir.glob("session_*.md"), key=os.path.getmtime)
            while len(sessions) > 20:
                oldest = sessions.pop(0)
                try:
                    oldest.unlink()
                except FileNotFoundError:
                    pass # Race condition: Outro processo já deletou o arquivo, ignorar.
        except Exception as e:
            self.console.print(f"[dim yellow]⚠️  Falha na rotação de logs de sessão: {e}[/]")

    def _trigger_auto_train(self):
        """Executa o retreinamento do modelo automaticamente."""
        try:
            # Resolve caminho do binário ou script para garantir execução em dev/prod
            local_bin = common.get_project_root() / "bin" / "aponte"
            trainer_script = common.get_project_root() / "core" / "services" / "knowledge" / "trainer.py"

            cmd = []
            if local_bin.exists():
                cmd = [str(local_bin), "ai", "train"]
            elif trainer_script.exists():
                cmd = [sys.executable, str(trainer_script)]
            else:
                cmd = ["aponte", "ai", "train"]

            if cmd:
                # Executa o treinamento em background para não bloquear a saída do usuário.
                # Redireciona output para /dev/null para não poluir o terminal que está sendo fechado.
                self.console.print("[dim]🧠 Disparando retreinamento (Neuroplasticidade) em background...[/dim]")
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        except Exception as e:
            self.log_error(f"Erro ao executar auto-train: {e}")

    def _handle_tool_execution(self, tool_name, tool_args, user_input):
        """
        Centraliza a execução de ferramentas para garantir consistência em:
        - Resolução de nomes
        - Auditoria
        - Tratamento de erros
        - Truncamento de histórico (Proteção de Contexto)

        Returns:
            str: The raw output from the tool execution.
        """
        name = tool_name # A resolução agora é responsabilidade do ToolManager/Graph

        # Feedback Visual
        args_str = f"\n[dim]Args: {json.dumps(tool_args, ensure_ascii=False)}[/dim]" if tool_args else ""
        self.console.print(
            Panel(f"🤖 Invocando Agente: [bold]{name}[/]{args_str}", border_style="magenta")
        )

        # Execução
        tool_output = self.tool_manager.execute_tool(name, self._get_context_variable, self._log_audit_event, tool_args=tool_args)

        # Garante string para processamento
        if tool_output is None: tool_output = ""
        tool_output = str(tool_output)
        clean_out = tool_output.strip()

        # Heurística de Diagnóstico (Lista Vazia)
        if "[]" in clean_out and "count" in clean_out and ":0" in clean_out:
             self.console.print("[dim yellow]💡 Dica: Lista vazia? Verifique se a Região AWS está correta ou se suas credenciais têm permissão.[/]")

        # Exibição (Truncada visualmente se necessário)
        display_out = tool_output[:2000] + ("..." if len(tool_output) > 2000 else "")
        self.console.print(Panel(display_out, title="Saída da Ferramenta", border_style="dim"))

        # Histórico (Truncado para economizar tokens)
        if len(clean_out) > 2000:
            history_output = clean_out[:800] + "\n... [SAÍDA TRUNCADA] ...\n" + clean_out[-800:]
        else:
            history_output = clean_out

        self.history.append({
            "u": user_input,
            "a": f"Executei a ferramenta: {name}. Resultado:\n{history_output}",
        })

        # The original return value was not being used.
        # Returning the full output to enable Phase 4 (Feedback Loop).
        return tool_output

    def _render_welcome_screen(self):
        """Renderiza o cabeçalho e status inicial da sessão."""
        self.console.rule(
            "[bold magenta]💬 Arquiteto Virtual (Multi-Tenant Ops)[/]"
        )

        self.console.print("[bold cyan]👋 Olá! Sou o Arquiteto Virtual.[/]")
        self.console.print(
            "[dim]Vamos desenhar sua infraestrutura. Me conte o que você precisa.[/dim]"
        )
        self.console.print(
            "[dim]Comandos: 'sair', '/ls [dir]', '/tree'.[/dim]"
        )
        self.console.print(
            "[dim italic]💰 Custo da IA: Free Tier (Google AI Studio) | Custo da Infra AWS: Variável (Use Infracost)[/dim italic]\n"
        )

        # --- STATUS DO CÉREBRO ---
        active_model = llm_client.get_active_model()
        display_model = llm_client.get_display_name(active_model)

        if llm_client.AI_PROVIDER == "openrouter" or llm_client.AI_PROVIDER == "google":
            provider_sub = f"[dim]Rodando na nuvem via OpenRouter[/dim]"
        else:
            ollama_ver = llm_client.ollama.get_version()
            provider_sub = f"[dim]Rodando em localhost via Ollama (v{ollama_ver})[/dim]"
            if ollama_ver.startswith("0.1") or ollama_ver == "unknown":
                provider_sub += "\n[bold red]⚠️  Versão antiga detectada! Atualize para v0.3+[/]"

        aws_region, aws_account = self._detect_aws_identity()
        aws_info = f"[dim]AWS Region: {aws_region} | Account: {aws_account}[/dim]"

        if active_model and "aponte-ai" in active_model:
            self.console.print(
                Panel(
                    f"🧠 Cérebro Ativo: [bold magenta]{display_model}[/] (Especializado)\n{provider_sub}\n{aws_info}",
                    border_style="green",
                )
            )
        else:
            self.console.print(
                Panel(
                    f"🧠 Cérebro Ativo: [bold yellow]{display_model}[/] (Genérico)\n{provider_sub}\n{aws_info}\n[dim]Recomendação: Execute 'aponte ai train' para especializar.[/dim]",
                    border_style="yellow",
                )
            )

    def _handle_slash_commands(self, user_input):
        """Processa comandos de sistema iniciados por /."""
        # Comando /ls para listar arquivos
        if user_input.startswith("/ls"):
            path_str = user_input[3:].strip().strip('"').strip("'")
            root = common.get_project_root()
            target = root / path_str if path_str else root

            if not target.exists() or not target.is_dir():
                self.console.print(f"[red]Diretório inválido: {path_str}[/]")
                return True

            self.console.print(f"[bold cyan]📂 Conteúdo de {target.name}:[/]")
            for p in sorted(target.glob("*")):
                if p.name.startswith(".") or p.name == "__pycache__":
                    continue
                icon = "📁" if p.is_dir() else "📄"
                if p.name == "projects":
                    self.console.print(f" {icon} [bold yellow]{p.name}[/] (Core/Tenants)")
                else:
                    self.console.print(f" {icon} {p.name}")
            return True

        # Comando /tree para visualizar estrutura
        if user_input.strip() == "/tree":
            root = common.get_project_root()
            tree = Tree(f"[bold gold1]📂 {root.name}[/]")
            # Lógica de construção da árvore simplificada para visualização rápida
            # (Mantendo a lógica original mas encapsulada)
            self._build_visual_tree(root, tree)
            self.console.print(tree)
            return True
        return False

    def _build_visual_tree(self, path, tree_node, depth=0):
        if depth > 2: return
        for p in sorted(path.glob("*")):
            if p.name.startswith(".") or p.name in ["node_modules", "venv", "__pycache__", ".git"]:
                continue
            if p.is_dir():
                branch = tree_node.add(f"📁 [bold]{p.name}[/]")
                self._build_visual_tree(p, branch, depth + 1)
            else:
                tree_node.add(f"📄 {p.name}")

    def run(self):
        self._preload_context() # Lazy Loading: Movemos para cá para não bloquear __init__
        self._render_welcome_screen()

        last_code_block = ""

        while True:
            try:
                if self.initial_input:
                    user_input = self.initial_input
                    self.console.print(f"\n[bold green]Você[/]: {user_input}")
                    self.initial_input = None
                else:
                    user_input = Prompt.ask("\n[bold green]Você[/]")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[yellow]👋 Encerrando sessão (EOF)...[/]")
                break

            # Normalização robusta para comandos de saída (remove espaços e aspas)
            clean_input = user_input.strip().lower().replace('"', "").replace("'", "")

            if clean_input in ["sair", "exit", "quit", "tchau", "bye"]:
                self._save_session_memory()
                if self.history:
                    self._trigger_auto_train()

                self.console.print("[dim]🧹 Limpando contexto da sessão para 'home'...[/dim]")

                common.reset_context() # Garante que a próxima sessão inicie neutra (ADR-027)

                self.console.print("[yellow]👋 Encerrando sessão...[/]")
                break

            if self._handle_slash_commands(user_input):
                continue

            # 0. Sistema de Reflexo (Bypass LLM)
            # "Dark Layer": Implementação de System 1 (Rápido) vs System 2 (Lento/LLM)
            reflex_match = self.reflex_engine.get_command(user_input)
            if reflex_match:
                reflex_cmd, extension, tool_args, is_destructive = reflex_match

                # Fase 3: Confirmação de Segurança (Human-in-the-loop)
                if is_destructive:
                    if not Prompt.ask(
                        f"[bold yellow]🚨 Ação Destrutiva/Modificadora: '{reflex_cmd}'. Deseja continuar?[/]",
                        choices=["s", "n"],
                        default="n",
                    ) == "s":
                        self.console.print("[red]⛔ Operação cancelada pelo usuário.[/]")
                        continue # Volta para o loop do prompt

                # Auto-load extension if the tool is not yet registered (lazy loading)
                if reflex_cmd not in self.tool_manager.tools_registry:
                    self.console.print(f"[dim]⚡ Reflexo ativado. Carregando extensão '{extension}' para a ferramenta '{reflex_cmd}'...[/dim]")
                    self.tool_manager._execute_load_extension({"extension": extension})

                # FIX: Adiciona spinner para dar feedback visual em comandos demorados (prowler, etc)
                with self.console.status(f"[bold green]⚙️  Executando '{reflex_cmd}'... Esta operação pode demorar.[/]"):
                    tool_output = self._handle_tool_execution(reflex_cmd, tool_args, user_input)

                # Fase 4: Feedback Loop (Fallback to System 2)
                # Detecta erros padronizados (⛔) ou genéricos ("Erro", "Error") para acionar a IA
                is_error = not tool_output or (tool_output.strip().startswith("⛔") or "Erro" in tool_output or "Error" in tool_output)

                if is_error:
                    self.console.print("[dim]⚡ Reflexo falhou. Acionando Sistema 2 (IA) para análise...[/dim]")
                    # O erro já está no histórico. O input original é suficiente para o LLM entender.
                    # Deixa o código fluir para o GraphArchitect.
                elif reflex_cmd == "access_knowledge":
                    # Fase 5: RAG Summarization (Reflex with Generation)
                    with self.console.status("[bold green]🤖 Sintetizando resposta...[/]"):
                        # OTIMIZAÇÃO: Trunca o contexto para evitar timeouts em hardware modesto (CPU)
                        # Limita a ~3000 caracteres (aprox 750 tokens) para garantir resposta rápida
                        safe_context = tool_output[:3000] + "... [TRUNCADO]" if len(tool_output) > 3000 else tool_output

                        prompt = f"""
                        Com base no CONTEXTO abaixo, responda à PERGUNTA do usuário de forma concisa e direta.

                        CONTEXTO:
                        {safe_context}

                        PERGUNTA:
                        {user_input}
                        """
                        # FIX: Envia lista de mensagens e extrai conteúdo do dicionário de resposta
                        response_payload = llm_client.chat([{"role": "user", "content": prompt}])
                        summarized_response = response_payload.get("content") if response_payload else None
                    if summarized_response:
                        self.console.print(Markdown(summarized_response))
                        self.history.append({"u": user_input, "a": summarized_response})
                    else:
                        # Fallback: Se a sumarização falhar (ex: timeout), exibe o contexto bruto.
                        self.console.print("[dim yellow]⚠️  A IA não conseguiu sintetizar uma resposta. Exibindo contexto bruto.[/dim yellow]")
                        self.console.print(Panel(tool_output, title="Saída da Ferramenta (Bruto)", border_style="dim"))
                        self.history.append({"u": user_input, "a": tool_output})
                    continue
                else:
                    # Fase 5: Humanização da Saída (Reflex with Interpretation)
                    # Transforma JSONs brutos em insights legíveis para o usuário.
                    if tool_output and len(tool_output.strip()) > 0:
                        with self.console.status("[bold green]🤖 Interpretando resultado...[/]"):
                            safe_context = tool_output[:3000] + "... [TRUNCADO]" if len(tool_output) > 3000 else tool_output

                            prompt = f"""
                            Analise a SAÍDA DA FERRAMENTA abaixo (pode ser JSON ou Texto) e gere um resumo legível em Markdown.

                            SAÍDA:
                            {safe_context}

                            TAREFA:
                            1. Se for JSON de recursos/logs: Liste os itens encontrados.
                            2. Se for um Relatório de Texto (ex: Checkov, TFSec): Resuma as vulnerabilidades encontradas ou confirme se passou.
                            3. IGNORE logs de infraestrutura como "Container Creating", "Pulling image", "Waiting".

                            FORMATO DA RESPOSTA (Markdown):
                            ✅ Resumo: [Resumo da ação]

                            [Detalhes/Lista se houver]

                            IMPORTANTE: NÃO gere JSON. Apenas texto.
                            """
                            response_payload = llm_client.chat([{"role": "user", "content": prompt}])
                            human_response = response_payload.get("content") if response_payload else None

                        if human_response:
                            self.console.print(Markdown(human_response))
                            # Atualiza a memória de curto prazo substituindo o JSON bruto pela explicação
                            if self.history:
                                self.history[-1]["a"] = human_response

                    continue # Sucesso, volta para o prompt do usuário

            # --- MIGRATION: LangGraph Orchestration ---
            with self.console.status(
                f"[bold green]🤖 Orquestrando ({llm_client.get_display_name()})...[/]",
                spinner="dots",
            ) as status:
                # Atualiza o callback para usar o status atual
                self.graph_architect.status_callback = lambda msg: status.update(f"[bold green]{msg}[/]")

                try:
                    # Converte histórico para formato LangChain
                    graph_messages = []
                    for h in self.history[-5:]: # OTIMIZAÇÃO: Reduzido de 10 para 5 para performance crítica
                        graph_messages.append(HumanMessage(content=h['u']))
                        graph_messages.append(AIMessage(content=h['a']))
                    graph_messages.append(HumanMessage(content=user_input))

                    # Invoca o Grafo
                    inputs = {"messages": graph_messages, "current_step": 0, "plan": [], "tool_outputs": {}, "error": None, "retry_count": 0}

                    # Configuração de Thread para Checkpointing (Obrigatório com MemorySaver)
                    # Aumentado para 100 para evitar GraphRecursionError em planos complexos ou loops de retry
                    config = {"configurable": {"thread_id": self.session_id}, "recursion_limit": 100}
                    final_state = self.graph_architect.graph.invoke(inputs, config=config)

                    # Validação Robusta do Estado (Problema #5)
                    if not final_state or 'messages' not in final_state or not final_state['messages']:
                        self.console.print("[bold red]❌ Erro no Grafo Cognitivo: O estado final retornado é inválido ou vazio.[/]")
                        response = ""
                    else:
                        # Extrai resposta final
                        response = final_state['messages'][-1].content
                except Exception as e:
                    # Self-Healing Cognitivo: Intercepta limites de recursão/loop
                    if "recursion limit" in str(e).lower() or "GraphRecursionError" in str(type(e)):
                        self.console.print(
                            Panel(
                                "[bold yellow]🔄 Limite de Raciocínio Atingido (Cognitive Overload)[/bold yellow]\n\n"
                                "[dim]A IA entrou em um loop de pensamento ou a tarefa é muito complexa para o limite de passos atual.\n"
                                "Isso é comum em modelos locais menores. Tente dividir sua solicitação em etapas menores.[/dim]",
                                title="Auto-Proteção", border_style="yellow"
                            )
                        )
                        response = "⚠️ **Limite de Raciocínio Atingido:** Não consegui concluir o plano completo. Por favor, tente dividir sua solicitação em tarefas menores (ex: 'Crie a VPC' primeiro, depois 'Crie o EC2')."
                        # Não relança o erro, permite que o chat continue
                    else:
                        # Log completo para depuração de outros erros
                        tb_str = traceback.format_exc()
                        self.log_error(f"Erro crítico no Grafo Cognitivo: {e}\n{tb_str}")

                        # Mensagem clara para o usuário
                        self.console.print(
                            Panel(
                                f"[bold red]❌ Ocorreu um erro inesperado na orquestração da IA.[/]\n\n[dim]Detalhes técnicos foram salvos nos logs para análise. Por favor, tente reformular sua solicitação ou reinicie a sessão ('sair').\nErro: {e}[/dim]",
                                title="[bold red]Falha de Orquestração[/bold red]",
                                border_style="red"
                            )
                        )
                        response = ""


            if response:
                # 2. Extração de Código (HCL/Terraform)
                code_matches = self.parser.extract_code_blocks(response)
                if code_matches:
                    self.last_generated_code = code_matches[-1]
                    self.last_generated_filename = None # FIX: Reseta contexto de arquivo para evitar sobrescrita acidental por código de chat
                    last_code_block = self.last_generated_code

                # Hallucination Check (ADR-028): Intercepta sugestões de comandos manuais que violam o protocolo MCP
                if "```bash" in response or "```sh" in response:
                    if any(cmd in response for cmd in ["aws ", "git ", "terraform ", "gh "]):
                        self.console.print(
                            Panel(
                                "[bold yellow]⚠️ ALERTA DE ALUCINAÇÃO ⚠️[/bold yellow]\n\nA IA sugeriu a execução de comandos manuais (`aws`, `git`, etc.) em vez de usar as ferramentas internas, quebrando o fluxo de automação e segurança.\n\n[bold]Ação Recomendada:[/bold] Reformule sua solicitação para ser mais direta, focando na ação e não em como executá-la.\nEx: 'liste os buckets s3' em vez de 'rode o comando para listar buckets'.",
                                title="[bold red]Interceptor de Comportamento[/bold red]",
                                border_style="red",
                                expand=False
                            )
                        )

                self.console.print(Markdown(response))
                self.history.append({"u": user_input, "a": response})
            else:
                self.console.print(
                    "[dim yellow]⚠️  (Sem resposta da IA ou Timeout)[/dim yellow]"
                )
                # Adiciona ao histórico mesmo vazio para manter consistência
                self.history.append({"u": user_input, "a": "..."})


if __name__ == "__main__":
    # UX: Abre em novo terminal para facilitar a visualização e interação
    # Verifica se já foi spawnado ou se está em ambiente não-interativo
    is_spawned = os.environ.get("APONTE_CHAT_SPAWNED") == "1"
    is_interactive = sys.stdin.isatty()

    if is_interactive and not is_spawned and "--no-spawn" not in sys.argv:
        system = platform.system()
        env = os.environ.copy()
        env["APONTE_CHAT_SPAWNED"] = "1"
        script_path = str(Path(__file__).resolve())

        if system == "Windows":
            # Usa CREATE_NEW_CONSOLE para evitar problemas de aspas com shell=True
            # cmd /k mantem a janela aberta se o script falhar
            subprocess.Popen(
                ["cmd", "/k", sys.executable, script_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=env,
            )
            sys.exit(0)
        elif system == "Linux":
            # Tenta encontrar um emulador de terminal disponível
            for term in ["gnome-terminal", "konsole", "xterm", "tilix"]:
                if subprocess.run(["which", term], capture_output=True).returncode == 0:
                    args = (
                        [term, "--", sys.executable, script_path]
                        if term == "gnome-terminal"
                        else [term, "-e", sys.executable, script_path]
                    )
                    subprocess.Popen(args, env=env)
                    sys.exit(0)

    # Gestão de Ciclo de Vida para o Chat
    try:
        # Captura argumentos da CLI (ex: input do Quick Chat)
        args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
        initial_input = " ".join(args) if args else None

        llm_client.start_server()
        agent = ArchitectAgent(initial_input=initial_input)
        agent.run()
    finally:
        if 'agent' in locals():
            agent.cleanup()
        llm_client.stop_server()
