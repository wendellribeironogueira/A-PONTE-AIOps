import json
import os
import re
import shlex
import threading
import subprocess  # nosec B404 - Used for safe, reviewed CLI tool execution.
import sys

from rich.console import Console
from rich.prompt import Prompt

from core.lib import toolbelt as tools
from core.lib import utils as common
from core.lib.mcp import MCPClient
from core.lib.runtime import ContainerManager


class ToolManager:
    """
    Gerenciador de Ferramentas MCP.
    Responsável pelo ciclo de vida dos clientes MCP, descoberta de ferramentas
    e execução segura de comandos.
    """

    def __init__(self, console: Console):
        self.console = console
        self.mcp_clients = {}
        self.tools_registry = {}  # Mapa { "tool_name": client_instance }
        self.tool_extension_map = {} # Mapa { "tool_name": "extension_name" }
        self.tools_definitions = []  # Schemas para o Prompt
        self.all_tools_definitions = []  # Registro Completo (Para Lookup)
        self.resources_map = {}  # OTIMIZAÇÃO: Índice O(1) para recursos { "uri": resource_def }
        self.resources_definitions = []  # Registry de Recursos MCP
        self.prompts_definitions = []  # Registry de Prompts MCP
        self.container_manager = ContainerManager()

        # Circuit Breaker State
        self.failure_counts = {}
        self.MAX_FAILURES = 3
        self.TOOL_TIMEOUT_SECONDS = 900 # 15 minutos

        # Define ferramentas essenciais que sempre estarão no contexto (Low Latency)
        self.core_tools = {
            "lookup_tools", "load_extension", "unload_extension",
            "read_file", "save_file", "list_directory", "generate_code", # Dev
            "check_registry_availability", "normalize_name", # Project
            "get_platform_status", "list_projects", "check_health", # Server
            "aws_check_cloudtrail", # AWS (Status Only - Outros via load_extension)
            "access_knowledge", # Knowledge (Pull Model)
            "web_search", # Research (Internet Access)
            "read_resource" # System (Resource Reader)
        }

        # Registra ferramenta de descoberta (Meta-Tool)
        lookup_tool_def = {
            "type": "function",
            "function": {
                "name": "lookup_tools",
                "description": "Mecanismo de busca de emergência (Fallback). Use APENAS se você não encontrar a ferramenta necessária no Catálogo Global ou nas ferramentas ativas.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Termo de busca (ex: 'aws', 'git', 'bucket')"}},
                    "required": ["query"]
                }
            }
        }
        self.tools_definitions.append(lookup_tool_def)
        self.all_tools_definitions.append(lookup_tool_def)
        self.tool_extension_map["lookup_tools"] = "system"

        # Registra ferramenta de carregamento dinâmico (Phase 3)
        load_ext_def = {
            "type": "function",
            "function": {
                "name": "load_extension",
                "description": "Carrega ferramentas especializadas (AWS, Git, Security). EXECUTE IMEDIATAMENTE se o usuário solicitar uma ação que requer ferramentas destas categorias e elas não estiverem disponíveis.",
                "parameters": {
                    "type": "object",
                    "properties": {"extension": {"type": "string", "enum": ["aws", "git", "terraform", "security", "research", "ops"]}},
                    "required": ["extension"]
                }
            }
        }
        self.tools_definitions.append(load_ext_def)
        self.all_tools_definitions.append(load_ext_def)
        self.tool_extension_map["load_extension"] = "system"

        # Registra ferramenta de descarregamento (Phase 3.1)
        unload_ext_def = {
            "type": "function",
            "function": {
                "name": "unload_extension",
                "description": "Remove ferramentas de uma extensão do contexto. Use para liberar memória após concluir tarefas pesadas.",
                "parameters": {
                    "type": "object",
                    "properties": {"extension": {"type": "string", "enum": ["aws", "git", "terraform", "security", "research", "ops"]}},
                    "required": ["extension"]
                }
            }
        }
        self.tools_definitions.append(unload_ext_def)
        self.all_tools_definitions.append(unload_ext_def)
        self.tool_extension_map["unload_extension"] = "system"

        # Registra ferramenta de leitura de recursos (Generic)
        read_res_def = {
            "type": "function",
            "function": {
                "name": "read_resource",
                "description": "Lê o conteúdo de um recurso do sistema (URI).",
                "parameters": {
                    "type": "object",
                    "properties": {"uri": {"type": "string", "description": "URI do recurso (ex: aws://identity, aponte://docs/adrs)"}},
                    "required": ["uri"]
                }
            }
        }
        self.tools_definitions.append(read_res_def)
        self.all_tools_definitions.append(read_res_def)
        self.tool_extension_map["read_resource"] = "system"

        # Mapa de despacho para ferramentas internas (Refatoração para OCP)
        self.internal_tools = {
            "lookup_tools": self._execute_lookup_tools,
            "load_extension": self._execute_load_extension,
            "unload_extension": self._execute_unload_extension,
            "read_resource": self._execute_read_resource,
        }

        # Inicializa clientes
        self._register_clients()

    # Definição centralizada de prefixos de extensões (DRY & Efficiency)
    EXTENSION_PREFIXES = {
        "aws": "aws_",
        "git": "git_",
        "terraform": "tf_",
        "security": ["tfsec", "checkov", "tflint", "trivy", "prowler", "run_security_audit"],
        "research": ["web_search", "read_url"],
        "snippets": ["list_snippets", "get_snippet"],
        "ops": ["diagnose_system", "detect_drift", "estimate_cost", "run_pipeline", "train_knowledge_base", "ingest_sources", "clean_cache"]
    }

    def cleanup(self):
        """Encerra todos os processos MCP iniciados."""
        self.console.print("[dim]🧹 Encerrando conexões MCP...[/dim]")
        for _, client in self.mcp_clients.items():
            if client and hasattr(client, "process") and client.process:
                client.process.terminate()

    def get_client(self, namespace):
        return self.mcp_clients.get(namespace)

    def _get_mcp_command(self, script_name):
        return self.container_manager.get_execution_command(script_name)

    def _register_clients(self):
        """Registra todos os clientes MCP e descobre suas ferramentas."""
        self._register_client("core", self._init_core_mcp())
        self._register_client("terraform", self._init_terraform_mcp())
        self._discover_extra_mcp_services()

    def _register_client(self, namespace, client):
        if not client:
            return

        self.mcp_clients[namespace] = client
        try:
            tools_list = client.list_tools()
            for tool in tools_list:
                name = tool.get("name")
                self.tool_extension_map[name] = namespace
                self.tools_registry[name] = client

                schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
                if "type" not in schema:
                    schema["type"] = "object"

                tool_def = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.get("description", ""),
                        "parameters": schema,
                    },
                }

                # Adiciona ao registro completo (evitando duplicatas)
                if not any(t["function"]["name"] == name for t in self.all_tools_definitions):
                    self.all_tools_definitions.append(tool_def)

                # OTIMIZAÇÃO: Por padrão, carrega apenas as ferramentas 'core' no contexto ativo
                # para reduzir a carga cognitiva em modelos menores. Outras ferramentas são carregadas
                # sob demanda via `load_extension`.
                if name in self.core_tools and not any(t["function"]["name"] == name for t in self.tools_definitions):
                    self.tools_definitions.append(tool_def)

            if hasattr(client, "list_resources"):
                try:
                    res_list = client.list_resources()
                    for res in res_list:
                        res["_client"] = client
                        self.resources_definitions.append(res)
                        self.resources_map[res.get("uri")] = res # Indexa para busca rápida
                except Exception as e:
                    self.console.print(
                        f"[dim red]Erro ao listar recursos de {namespace}: {e}[/dim red]"
                    )

            if hasattr(client, "list_prompts"):
                try:
                    prompts_list = client.list_prompts()
                    for p in prompts_list:
                        p["_client"] = client
                        self.prompts_definitions.append(p)
                except Exception as e:
                    self.console.print(
                        f"[dim red]Erro ao listar prompts de {namespace}: {e}[/dim red]"
                    )
        except Exception as e:
            self.console.print(
                f"[dim red]Erro ao listar ferramentas de {namespace}: {e}[/dim red]"
            )

    def _discover_extra_mcp_services(self):
        try:
            root = common.get_project_root()
            services_dir = root / "core" / "services"
            explicit_scripts = {
                "mcp_terraform.py", # Handled explicitly (Docker)
                "mcp_manager.py",   # Manager logic, not a service (Evita recursão)
            }

            if not services_dir.exists():
                return

            for script_path in services_dir.glob("mcp_*.py"):
                if script_path.name in explicit_scripts:
                    continue

                namespace = script_path.stem.replace("mcp_", "")
                if namespace in self.mcp_clients:
                    continue

                self.console.print(
                    f"[dim]🔌 Auto-Discovery: Carregando serviço extra '{namespace}'...[/dim]"
                )
                try:
                    module_name = f"core.services.{script_path.stem}"
                    command = [sys.executable, "-m", module_name]
                    # Silent=False para expor erros de importação (Broken Pipe) no console durante o boot
                    client = MCPClient(command=command, silent=False, cwd=str(root))
                    client.start()
                    self._register_client(namespace, client)
                    self.console.print(f"[dim]   ✅ Serviço '{namespace}' registrado com sucesso.[/dim]")
                except BrokenPipeError:
                    # Tenta ler o erro real do processo filho
                    error_msg = "Sem detalhes."
                    if client.process and client.process.stderr:
                        error_msg = client.process.stderr.read()
                    self.console.print(
                        f"[dim red]❌ Falha Crítica: O serviço '{namespace}' crashou na inicialização.\nErro: {error_msg.strip()}[/dim red]"
                    )
                except Exception as e:
                    self.console.print(
                        f"[dim red]Falha ao carregar serviço dinâmico {namespace}: {e}[/dim red]"
                    )
        except Exception as e:
            self.console.print(
                f"[dim red]Erro no discovery de serviços MCP: {e}[/dim red]"
            )

    # --- Init Methods ---
    def _init_terraform_mcp(self, retry=True):
        client = None
        command = []
        try:
            command = self._get_mcp_command("mcp_terraform.py")

            # FIX: Redireciona para o entrypoint.sh que configura o ambiente e localiza o script
            if command and command[-1] == "mcp_terraform.py":
                command[-1] = "/usr/local/bin/entrypoint.sh"

            client = MCPClient(command=command, silent=True)
            client.start()
            return client
        except Exception as e:
            msg = str(e)
            if "Broken pipe" in msg:
                 msg = f"O container Docker ou script Python crashou na inicialização (Broken Pipe).\nCommand: {command}"
                 # Tenta capturar stderr para diagnóstico
                 if client and hasattr(client, 'process') and client.process and client.process.stderr:
                     try:
                         err = client.process.stderr.read()
                         if err:
                             msg += f"\n[dim]Stderr: {err.strip()}[/dim]"
                     except:
                         pass

            if "Diretório /app está vazio" in msg:
                self.console.print("\n[bold yellow]🔧 Diagnóstico: Volume Docker Desconectado[/bold yellow]")
                self.console.print("[dim]🚑 Auto-Healing: Tentando reconectar o volume automaticamente...[/dim]")
                try:
                    root = common.get_project_root()
                    compose_file = root / "config" / "containers" / "docker-compose.yml"
                    subprocess.run(
                        ["docker", "compose", "-f", str(compose_file), "up", "-d", "--force-recreate", "mcp-terraform"],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self.console.print("[bold green]✅ Volume reconectado! Reiniciando cliente...[/bold green]")
                    if retry: return self._init_terraform_mcp(retry=False)
                except Exception as heal_err:
                    self.console.print(f"[bold red]❌ Falha no Auto-Healing: {heal_err}[/bold red]")
                    self.console.print(f"👉 Execute manualmente: docker compose -f {str(compose_file)} up -d --force-recreate mcp-terraform\n")

            self.console.print(f"[dim red]❌ Falha ao iniciar MCP Terraform: {msg}[/dim red]")
            return None

    def _init_core_mcp(self):
        try:
            root = common.get_project_root()
            # Executa como módulo para garantir imports corretos
            command = [sys.executable, "-m", "core.server"]
            client = MCPClient(command=command, silent=True, cwd=str(root))
            client.start()
            return client
        except Exception as e:
            self.console.print(f"[dim red]❌ Falha ao iniciar MCP Core: {e}[/dim red]")
            return None

    # --- Execution Logic ---
    def execute_tool(self, command, context_resolver, audit_logger, tool_args=None):
        """Executa uma ferramenta CLI e retorna a saída."""
        clean_cmd = command.strip()

        try:
            # 1. Parsing Unificado (String vs Dict)
            if tool_args is not None:
                tool_name = clean_cmd
                args = tool_args
                ignored_parts = []
            else:
                tool_name, args, ignored_parts = self._parse_tool_arguments(clean_cmd)

            # FIX: Sanitização de alucinações de variáveis (ex: var.project_name)
            # Se o modelo passar a variável literal, tentamos resolver ou removemos para não quebrar filtros.
            if isinstance(args, dict):
                for k, v in list(args.items()):
                    if isinstance(v, str) and v.startswith("var."):
                        resolved = context_resolver(v.replace("var.", ""))
                        if resolved:
                            args[k] = resolved
                        else:
                            del args[k]

            # AUTO-DISCOVERY / PERMISSIVE EXECUTION
            # Verifica se a ferramenta existe em algum cliente MCP registrado,
            # mesmo que não esteja carregada no contexto atual (Lazy Loading).
            client = self.tools_registry.get(tool_name)
            if not client:
                namespace = self.tool_extension_map.get(tool_name)
                if namespace:
                    client = self.mcp_clients.get(namespace)
                    if client:
                        self.tools_registry[tool_name] = client

            # FIX: Fallback de Auto-Correção para Reflexos
            # Se a ferramenta não foi encontrada mas sabemos que ela existe (via prefixo),
            # tentamos forçar o vínculo com o cliente correto.
            if not client and "_" in tool_name:
                prefix = tool_name.split("_")[0] # ex: aws, git
                # Tenta encontrar um cliente que tenha esse prefixo no nome (ex: aws_reader)
                for ns, cli in self.mcp_clients.items():
                    if ns.startswith(prefix):
                        self.tools_registry[tool_name] = cli
                        client = cli
                        break

            # SIMPLIFICAÇÃO: Se a ferramenta está no registro (carregada via MCP) ou é um comando interno, é permitida.
            # Remove a necessidade de manter uma allowlist manual redundante.
            is_registered = client is not None or tool_name in self.internal_tools or tool_name in self.core_tools or tool_name == "aponte" or tool_name.startswith("aponte ")
            is_allowed = is_registered

            if tool_name in self.internal_tools:
                return self.internal_tools[tool_name](args)

            # Circuit Breaker Check
            if self.failure_counts.get(tool_name, 0) >= self.MAX_FAILURES:
                return f"⛔ CIRCUIT BREAKER: A ferramenta '{tool_name}' falhou {self.MAX_FAILURES} vezes consecutivas e foi bloqueada temporariamente. Execute 'check_health' para diagnosticar."

            if not is_allowed:
                # audit_logger(
                #     tool_name, clean_cmd, "Blocked by Allowlist", status="BLOCKED"
                # )
                # return f"⛔ Ação Bloqueada: O comando '{clean_cmd}' não está na lista de ferramentas permitidas."
                self.console.print(f"[dim yellow]⚠️  Aviso: Comando '{tool_name}' não registrado. Tentando execução direta (Shell)...[/dim yellow]")
        except ValueError as e:
            return f"⛔ Erro de Sintaxe no Comando: {e}"

        if client:
            output = ""
            handler = self._get_mcp_handler(tool_name)
            output = handler(tool_name, args, ignored_parts, client, context_resolver)

            # Circuit Breaker Update (Heurística de Erro)
            if output.startswith("⛔") or "Erro" in output or "Error" in output:
                 self.failure_counts[tool_name] = self.failure_counts.get(tool_name, 0) + 1
            else:
                 self.failure_counts[tool_name] = 0

            audit_logger(tool_name, clean_cmd, output)
            return output

        # Fallback para execução local (subprocess)
        return self._execute_local_subprocess(tool_name, args, clean_cmd, context_resolver, audit_logger)

    def _execute_local_subprocess(self, tool_name, args, clean_cmd, context_resolver, audit_logger):
        """Executa ferramentas locais via subprocesso com streaming de saída."""
        if args is not None:
            exec_cmd = tool_name
            for k, v in args.items():
                exec_cmd += f" {k}={shlex.quote(str(v))}"
        else:
            exec_cmd = clean_cmd

        self.console.print(f"[dim]⚙️ Executando ferramenta: {exec_cmd}[/dim]")
        try:
            cmd_args = shlex.split(exec_cmd)
            cmd_args[0] = common.resolve_local_binary(cmd_args[0])

            env = os.environ.copy()
            for var in [
                "project_name",
                "environment",
                "app_name",
                "resource_name",
                "aws_region",
                "account_id",
            ]:
                val = context_resolver(var)
                if val:
                    env[f"TF_VAR_{var}"] = val

            # STREAMING EXECUTION (UX: Feedback visual em tempo real)
            process = subprocess.Popen(  # nosec B603
                cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            output_lines = []

            # OTIMIZAÇÃO: Leitura em thread separada para garantir que o timeout funcione
            # mesmo se o processo travar sem fechar o stdout.
            def read_stdout():
                if process.stdout:
                    for line in process.stdout:
                        self.console.print(line, end="", style="dim")
                        output_lines.append(line)

            reader = threading.Thread(target=read_stdout)
            reader.start()
            reader.join(timeout=self.TOOL_TIMEOUT_SECONDS)

            if reader.is_alive():
                process.kill()
                reader.join()
                audit_logger(tool_name, clean_cmd, "Timeout", status="ERROR")
                return f"⛔ Erro: A ferramenta '{tool_name}' excedeu o tempo limite de {self.TOOL_TIMEOUT_SECONDS}s e foi interrompida."

            process.wait() # Garante que o processo zumbi seja limpo
            output = "".join(output_lines).strip()

            # Circuit Breaker Update
            if output.startswith("⛔") or "Erro" in output or "Error" in output:
                 self.failure_counts[tool_name] = self.failure_counts.get(tool_name, 0) + 1
            else:
                 self.failure_counts[tool_name] = 0

            audit_logger(tool_name, clean_cmd, output)
            return output
        except Exception as e:
            self.failure_counts[tool_name] = self.failure_counts.get(tool_name, 0) + 1
            audit_logger(tool_name, clean_cmd, str(e), status="ERROR")
            return f"Erro ao executar ferramenta: {e}"

    def _parse_tool_arguments(self, command):
        """Parser robusto para argumentos de ferramentas (key=value, key = value)."""
        parts = shlex.split(command)
        tool_name = parts[0]
        args = {}
        ignored_parts = []

        i = 1
        while i < len(parts):
            part = parts[i]
            if "=" in part:
                k, v = part.split("=", 1)
                if not v and i + 1 < len(parts):  # Caso 'key= value'
                    v = parts[i + 1]
                    i += 1
                args[k] = v
            elif i + 1 < len(parts) and parts[i + 1] == "=":  # Caso 'key = value'
                if i + 2 < len(parts):
                    args[part] = parts[i + 2]
                    i += 2
                else:
                    ignored_parts.append(part)  # '=' no final sem valor
            else:
                ignored_parts.append(part)
            i += 1

        return tool_name, args, ignored_parts

    def _get_mcp_handler(self, tool_name):
        if tool_name.startswith("tf_"):
            return self._execute_mcp_terraform
        if tool_name.startswith("git_"):
            return self._execute_mcp_git
        if tool_name.startswith("aws_"):
            return self._execute_mcp_aws
        if self.tool_extension_map.get(tool_name) == "knowledge":
            return self._execute_mcp_knowledge
        return self._execute_mcp_generic

    def _execute_mcp_terraform(self, tool_name, args, ignored_parts, client, context_resolver):
        try:
            if ignored_parts:
                self.console.print(
                    f"[yellow]⚠️  Aviso: Argumentos posicionais ignorados: {ignored_parts}. Use 'key=value'.[/]"
                )

            if tool_name == "tf_plan":
                for var in ["environment", "app_name", "resource_name"]:
                    val = context_resolver(var)
                    if val and var not in args:
                        args[var] = val

            session_project = context_resolver("project_name")
            if session_project:
                args["project_name"] = session_project

            if tool_name in ["tf_apply", "tf_rollback"]:
                project = args.get("project_name", "desconhecido")
                op_type = "DEPLOY" if tool_name == "tf_apply" else "ROLLBACK/DESTROY"
                self.console.print(f"\n[bold red]🚨 SOLICITAÇÃO CRÍTICA: {op_type}[/]")
                self.console.print(
                    f"A IA está solicitando execução no projeto: [bold cyan]{project}[/]"
                )

                # FIX: Bloqueia em ambientes não-interativos (CI/CD) para evitar travamento
                if not sys.stdin.isatty():
                    if os.getenv("APONTE_AUTO_APPROVE") == "true":
                        self.console.print(
                            f"[yellow]⚠️  Auto-Aprovação CI/CD detectada para {op_type}.[/yellow]"
                        )
                        args["authorization"] = "AUTORIZADO"
                    else:
                        return f"⛔ Ação Bloqueada: {op_type} requer aprovação interativa (TTY não detectado) ou APONTE_AUTO_APPROVE=true."

                if (
                    Prompt.ask(
                        f"Confirma a operação de {op_type} na AWS?",
                        choices=["s", "n"],
                        default="n",
                    )
                    == "s"
                ):
                    args["authorization"] = "AUTORIZADO"
                else:
                    return f"⛔ Ação Bloqueada: O usuário negou a autorização para {op_type}."

            result = client.call_tool(tool_name, args)
            content = result.get("content", [])
            if content:
                text_output = content[0].get("text", "")
                if (
                    "AlreadyExists" in text_output
                    or "DuplicateRecordException" in text_output
                ):
                    suggestion = "\n\n📢 DIAGNÓSTICO DE DRIFT:\n"
                    suggestion += "Alguns recursos já existem na AWS mas não estão no arquivo de estado (.tfstate).\n"
                    suggestion += "Isso acontece quando o bootstrap é rodado novamente sem o estado original.\n\n"
                    suggestion += "👉 SOLUÇÃO: Importe os recursos manualmente:\n"
                    matches = re.findall(r"with (module\.[^,]+)", text_output)
                    seen = set()
                    for addr in matches:
                        if addr not in seen:
                            suggestion += f"  terraform import {addr} <RESOURCE_ID>\n"
                            seen.add(addr)
                    suggestion += "\n(Substitua <RESOURCE_ID> pelo Nome/ARN/URL do recurso que aparece na mensagem de erro)"
                    text_output += suggestion
                return text_output
            return json.dumps(result)
        except Exception as e:
            return f"Erro na execução MCP: {e}"

    def _execute_mcp_knowledge(self, tool_name, args, ignored_parts, client, context_resolver):
        """Handler for knowledge tools that are project-agnostic."""
        try:
            if ignored_parts:
                self.console.print(
                    f"[yellow]⚠️  Aviso: Argumentos posicionais ignorados: {ignored_parts}. Use 'key=value'.[/]"
                )

            # Knowledge tools are project-agnostic, do not inject project_name.
            result = client.call_tool(tool_name, args)
            content = result.get("content", [])
            if content:
                return content[0].get("text", "")
            return json.dumps(result)
        except Exception as e:
            return f"Erro na execução MCP Knowledge: {e}"

    def _execute_standard_mcp_call(self, tool_name, args, ignored_parts, client, context_resolver, namespace="Generic"):
        """Helper unificado para execução de ferramentas MCP padrão (DRY)."""
        try:
            if ignored_parts:
                self.console.print(
                    f"[yellow]⚠️  Aviso: Argumentos posicionais ignorados: {ignored_parts}. Use 'key=value'.[/]"
                )

            # Lógica de Injeção de Projeto
            should_inject = True
            if namespace == "Generic" and tool_name in ["check_health", "get_platform_status", "list_projects", "lookup_tools"]:
                should_inject = False

            if should_inject:
                session_project = context_resolver("project_name")
                if session_project and session_project != "home":
                    args["project_name"] = session_project

            result = client.call_tool(tool_name, args)
            content = result.get("content", [])
            if content:
                return content[0].get("text", "")
            return json.dumps(result)
        except Exception as e:
            return f"Erro na execução MCP {namespace}: {e}"

    def _execute_mcp_git(self, tool_name, args, ignored_parts, client, context_resolver):
        # Lógica de Isolamento Git (Movida de _execute_standard_mcp_call para manter SRP)
        if tool_name == "git_clone":
            session_project = context_resolver("project_name")
            if session_project and session_project not in ["home", "a-ponte"]:
                dest = args.get("destination", "")
                repo_url = args.get("repo_url", "")
                repo_name = "repo"
                if dest:
                    repo_name = os.path.basename(dest.rstrip(os.sep))
                elif repo_url:
                    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

                expected_path = f"projects/{session_project}/repos/{repo_name}"
                if dest != expected_path:
                    self.console.print(
                        f"[dim]🛡️  Isolamento Git: Forçando destino para {expected_path}[/dim]"
                    )
                    args["destination"] = expected_path

        return self._execute_standard_mcp_call(tool_name, args, ignored_parts, client, context_resolver, namespace="Git")

    def _execute_mcp_aws(self, tool_name, args, ignored_parts, client, context_resolver):
        return self._execute_standard_mcp_call(tool_name, args, ignored_parts, client, context_resolver, namespace="AWS")

    def _execute_mcp_generic(self, tool_name, args, ignored_parts, client, context_resolver):
        return self._execute_standard_mcp_call(tool_name, args, ignored_parts, client, context_resolver, namespace="Generic")

    def _execute_mcp_git_legacy_removed(self, tool_name, args, ignored_parts, client, context_resolver):
        # Código legado removido em favor do _execute_standard_mcp_call
        try:
            if ignored_parts:
                self.console.print(
                    f"[yellow]⚠️  Aviso: Argumentos posicionais ignorados: {ignored_parts}. Use 'key=value'.[/]"
                )

            session_project = context_resolver("project_name")
            if session_project and session_project != "home":
                args["project_name"] = session_project
                if tool_name == "git_clone" and session_project not in [
                    "home",
                    "a-ponte",
                ]:
                    dest = args.get("destination", "")
                    repo_url = args.get("repo_url", "")
                    repo_name = "repo"
                    if dest:
                        repo_name = os.path.basename(dest.rstrip(os.sep))
                    elif repo_url:
                        repo_name = (
                            repo_url.rstrip("/").split("/")[-1].replace(".git", "")
                        )
                    expected_path = f"projects/{session_project}/repos/{repo_name}"
                    if dest != expected_path:
                        self.console.print(
                            f"[dim]🛡️  Isolamento Git: Forçando destino para {expected_path}[/dim]"
                        )
                        args["destination"] = expected_path

            result = client.call_tool(tool_name, args)
            content = result.get("content", [])
            if content:
                return content[0].get("text", "")
            return json.dumps(result)
        except Exception as e:
            return f"Erro na execução MCP Git: {e}"

    def _execute_lookup_tools(self, args):
        """Executa a busca de ferramentas (Meta-Tool)."""
        try:
            query = args.get("query", "").lower()
            if not query:
                return "Ferramentas disponíveis (Categorias): aws, git, terraform, security, ops, dev, knowledge. Use query='termo' para buscar detalhes."

            matches = []
            # FIX: Busca no registro completo, não apenas no contexto carregado
            query_tokens = query.split()
            for tool in self.all_tools_definitions:
                name = tool["function"]["name"]
                desc = tool["function"]["description"].lower()

                # Fuzzy Search: Score based on token matches
                score = 0
                for token in query_tokens:
                    if token in name.lower() or token in desc:
                        score += 1

                if score > 0:
                    matches.append((score, f"- {name}: {tool['function']['description']}"))

            if matches:
                # Sort by score descending
                matches.sort(key=lambda x: x[0], reverse=True)
                return "Ferramentas encontradas:\n" + "\n".join([m[1] for m in matches])
            return f"Nenhuma ferramenta encontrada para '{query}'. Tente termos como 'aws', 'file', 'git'."

        except Exception as e:
            return f"Erro na busca de ferramentas: {e}"

    def _match_extension(self, name, key):
        """Helper para verificar se uma ferramenta pertence a uma extensão."""
        criteria = self.EXTENSION_PREFIXES.get(key)
        if not criteria: return False
        if isinstance(criteria, list): return name in criteria
        return name.startswith(criteria)

    def _execute_load_extension(self, args):
        """Carrega ferramentas de uma extensão para o contexto ativo (Phase 3)."""
        try:
            ext = args.get("extension", "").lower()

            loaded_count = 0

            for tool in self.all_tools_definitions:
                name = tool["function"]["name"]
                # Evita duplicatas no contexto ativo
                if any(t["function"]["name"] == name for t in self.tools_definitions):
                    continue

                if self._match_extension(name, ext):
                    self.tools_definitions.append(tool)

                    # CORREÇÃO: Registra a ferramenta no registry de execução para que o allowlist funcione.
                    tool_namespace = self.tool_extension_map.get(name)
                    if tool_namespace and tool_namespace in self.mcp_clients:
                        self.tools_registry[name] = self.mcp_clients[tool_namespace]

                    loaded_count += 1

            if loaded_count > 0:
                return f"✅ Extensão '{ext}' carregada. {loaded_count} ferramentas disponíveis.\n\nINSTRUÇÃO DE SILÊNCIO: NÃO responda ao usuário confirmando o carregamento. NÃO diga 'Vou listar...'. EXECUTE a próxima ferramenta necessária para atender a solicitação original IMEDIATAMENTE."
            return f"⚠️ Nenhuma ferramenta nova encontrada para a extensão '{ext}' (ou já estavam carregadas)."
        except Exception as e:
            return f"Erro ao carregar extensão: {e}"

    def _execute_unload_extension(self, args):
        """Remove ferramentas de uma extensão do contexto ativo."""
        try:
            ext = args.get("extension", "").lower()

            unloaded_count = 0

            # Filtra ferramentas mantendo apenas as que NÃO pertencem à extensão (exceto core)
            new_definitions = []
            for tool in self.tools_definitions:
                name = tool["function"]["name"]
                if name in self.core_tools:
                    new_definitions.append(tool)
                    continue

                if self._match_extension(name, ext):
                    unloaded_count += 1
                else:
                    new_definitions.append(tool)

            self.tools_definitions = new_definitions

            if unloaded_count > 0:
                return f"✅ Extensão '{ext}' descarregada. {unloaded_count} ferramentas removidas do contexto."
            return f"⚠️ Nenhuma ferramenta encontrada para descarregar da extensão '{ext}'."
        except Exception as e:
            return f"Erro ao descarregar extensão: {e}"

    def get_global_catalog(self) -> str:
        """Gera um catálogo dinâmico e leve de todas as capacidades para o System Prompt."""
        catalog = []

        # 1. Agrupa ferramentas por extensão
        by_ext = {}
        for tool in self.all_tools_definitions:
            name = tool["function"]["name"]
            desc = tool["function"]["description"]
            ext = self.tool_extension_map.get(name, "core")

            # Ignora ferramentas do sistema/core que já são nativas
            if ext in ["system", "core"]:
                continue

            if ext not in by_ext:
                by_ext[ext] = []
            by_ext[ext].append(f"- {name}: {desc}")

        if by_ext:
            catalog.append("\n### 🔌 Catálogo de Extensões (Lazy Loading)")
            catalog.append("Ferramentas abaixo requerem carregamento. Se precisar de uma, use `load_extension(extension='...')`.")
            for ext, tools in sorted(by_ext.items()):
                catalog.append(f"\n#### Extensão: '{ext}'")
                catalog.extend(tools)

        # 2. Recursos (Resources)
        if self.resources_definitions:
            catalog.append("\n### 📦 Recursos de Leitura (Read-Only)")
            catalog.append("Dados disponíveis via `read_resource(uri='...')`:")
            for res in self.resources_definitions:
                uri = res.get("uri")
                desc = res.get("description", "")
                catalog.append(f"- {uri}: {desc}")

        return "\n".join(catalog)

    def enable_eager_mode(self):
        """
        Ativa o modo 'Local-First': Carrega todas as extensões principais imediatamente.
        Ideal para modelos locais (Ollama) onde não há custo por token de ferramenta.
        """
        extensions = ["aws", "git", "security", "ops", "terraform", "research"]
        for ext in extensions:
            self._execute_load_extension({"extension": ext})
        self.console.print(f"[dim]🚀 Eager Mode: {len(extensions)} extensões carregadas (Ollama Local).[/dim]")

    def _execute_read_resource(self, args):
        """Lê um recurso MCP de qualquer cliente registrado."""
        uri = args.get("uri")
        if not uri:
            return "⛔ Erro: URI não fornecida."

        res = self.resources_map.get(uri)
        if res:
            client = res.get("_client")
            if client and hasattr(client, "read_resource"):
                try:
                    result = client.read_resource(uri)
                    if isinstance(result, dict) and "contents" in result:
                        return result["contents"][0]["text"]
                    return str(result)
                except Exception as e:
                    return f"⛔ Erro ao ler recurso {uri}: {e}"

        return f"⛔ Recurso não encontrado: {uri}. Use 'lookup_tools' para ver disponíveis."
