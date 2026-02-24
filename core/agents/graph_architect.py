import json
import re
from typing import Annotated, List, TypedDict, Union, Dict, Any
import operator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:
    SqliteSaver = None
from langgraph.checkpoint.memory import MemorySaver

from core.services import llm_gateway
from core.lib.mcp_manager import ToolManager
from core.domain import prompts

# --- 1. Definição do Estado (Memória Estruturada) ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add] # Histórico da conversa
    plan: List[str]          # Lista de passos a executar
    current_step: int        # Índice do passo atual
    tool_outputs: Dict[str, Any] # Memória de resultados de ferramentas
    error: Union[str, None]  # Rastreamento de erros para auto-correção
    retry_count: int         # Contador de tentativas para o passo atual

class GraphArchitect:
    """
    Orquestrador Cognitivo baseado em Grafos (LangGraph).
    Substitui o loop linear por uma máquina de estados capaz de planejamento e auto-correção.
    """

    TRIVIAL_INPUT_THRESHOLD = 5 # Limite de tokens para short-circuit

    # Ferramentas Core que sempre devem estar disponíveis (Constante de Classe)
    CORE_TOOLS = {"load_extension", "lookup_tools", "read_file", "list_files", "ask_user", "read_resource"}

    def __init__(self, tool_manager: ToolManager, context_resolver=None, audit_logger=None, status_callback=None, db_path=None):
        self.tool_manager = tool_manager
        self.context_resolver = context_resolver or (lambda x: None)
        self.audit_logger = audit_logger or (lambda t, c, o, s="SUCCESS": None)
        self.status_callback = status_callback or (lambda x: None)

        # Setup checkpointing (persists graph state)
        if db_path and SqliteSaver:
            db_path.parent.mkdir(exist_ok=True)
            # SqliteSaver.from_conn_string retorna um Context Manager.
            self._memory_cm = SqliteSaver.from_conn_string(str(db_path))
            self.memory = self._memory_cm.__enter__()
        else:
            if db_path and not SqliteSaver:
                print("\n⚠️  Aviso: Checkpointing durável (`SqliteSaver`) não encontrado.")
                print("   Sua versão do `langgraph` pode estar desatualizada. Usando memória volátil.")
                print("   Para habilitar, atualize: pip install --upgrade langgraph\n")
            self.memory = MemorySaver()

        self.graph = self._build_graph()

    def cleanup(self):
        """Libera recursos (ex: conexões de banco de dados)."""
        if hasattr(self, "_memory_cm") and self._memory_cm:
            self._memory_cm.__exit__(None, None, None)

    def _get_context_block(self):
        """Constrói o bloco de contexto a partir do resolver."""
        project = self.context_resolver("project_name")
        env = self.context_resolver("environment")
        if project:
            return f"CONTEXTO ATUAL: Project='{project}', Environment='{env}'"
        return "CONTEXTO ATUAL: Não definido (Discovery Mode)"

    def _filter_tools(self, tools: List[Dict], task_description: str) -> List[Dict]:
        """
        Heurística para reduzir o número de ferramentas enviadas ao LLM (Context Window Optimization).
        Seleciona ferramentas cujos nomes tenham relevância semântica com a tarefa.
        """
        if not tools:
            return []

        task_lower = task_description.lower()
        task_tokens = set(re.findall(r'\w+', task_lower))

        # --- OTIMIZAÇÃO: Mapeamento de verbos PT -> EN ---
        # Isso resolve o problema onde "listar buckets" não encontrava "aws_list_buckets"
        # e causava alucinação ou loop de erro.
        TRANSLATIONS = prompts.TOOL_FILTER_TRANSLATIONS

        # Verbos comuns que geram ruído na busca (ex: "listar" casando com "aws_list_buckets" quando o usuário quer "ec2")
        COMMON_VERBS = prompts.TOOL_FILTER_COMMON_VERBS

        filtered = []

        # Normalização simples de plural (ex: buckets -> bucket) para melhorar o match
        search_tokens = set()
        for t in task_tokens:
            if t in TRANSLATIONS:
                search_tokens.add(TRANSLATIONS[t])
            if len(t) >= 2: # Ignora palavras muito curtas (a, o), mas mantem s3, ec2, ip
                # Se o token for um verbo comum e houver outros tokens mais específicos, ignoramos o verbo
                if t in COMMON_VERBS and len(task_tokens) > 1:
                    continue
                search_tokens.add(t)
                if t.endswith('s'):
                    search_tokens.add(t[:-1])

        for tool in tools:
            name = tool.get('function', {}).get('name', '').lower()

            # 1. Ferramentas Core
            if name in self.CORE_TOOLS:
                filtered.append(tool)
                continue

            # 2. Match por Token (Ex: "bucket" na tarefa e "aws_list_buckets" na ferramenta)
            if any(token in name for token in search_tokens):
                filtered.append(tool)
                continue

        # Fallback: Se não encontramos nenhuma ferramenta específica (apenas Core),
        # retornamos todas para garantir que o LLM possa explorar.
        # Mas se encontramos ALGO específico (ex: 'aws_s3_list' para 's3'), confiamos no filtro.
        has_specific_match = any(
            t.get('function', {}).get('name', '').lower() not in self.CORE_TOOLS
            for t in filtered
        )

        # If no specific tool is found, return only the core tools.
        # This forces the model to use `load_extension` or `lookup_tools`
        # instead of being overwhelmed by the full list, preventing hallucinations.
        if not has_specific_match:
            return [t for t in tools if t.get('function', {}).get('name', '').lower() in self.CORE_TOOLS]

        return filtered

    def _build_planner_prompt(self, context_block, user_input, is_specialized):
        if is_specialized:
            return prompts.PLANNER_SPECIALIZED.format(
                context_block=context_block,
                user_input=user_input
            )
        else:
            return prompts.PLANNER_GENERIC.format(
                context_block=context_block,
                user_input=user_input
            )

    def _build_executor_prompt(self, context_block, step_idx, plan, current_task, context, is_specialized, previous_error, retry_count, last_msg):
        prompt_directives = ""
        if is_specialized:
            prompt_directives = prompts.EXECUTOR_DIRECTIVES_SPECIALIZED
        else:
            prompt_directives = prompts.EXECUTOR_DIRECTIVES_GENERIC

        prompt = prompts.EXECUTOR_BASE.format(
            context_block=context_block,
            prompt_directives=prompt_directives,
            step_idx=step_idx + 1,
            total_steps=len(plan),
            current_task=current_task,
            context_json=json.dumps(context, default=str)[:2000]
        )

        if previous_error:
            prompt += f"\n\n⚠️ ATENÇÃO: A tentativa anterior falhou com o erro: '{previous_error}'.\nAnalise o erro e tente uma abordagem diferente ou corrija os parâmetros da ferramenta."

        if isinstance(last_msg, HumanMessage):
            prompt += "\n\nOBSERVAÇÃO CRÍTICA: Você acabou de receber a saída da ferramenta solicitada acima. NÃO chame a mesma ferramenta novamente. Analise o resultado JSON e conclua este passo."

        if retry_count > 0:
            prompt += "\n\n⚠️ VOCÊ ESTÁ FALHANDO EM GERAR UMA CHAMADA DE FERRAMENTA VÁLIDA. Pare de explicar. Responda APENAS com o JSON da tool_call."

        return prompt

    def _build_critic_prompt(self, current_task, last_message):
        return prompts.CRITIC_BASE.format(
            current_task=current_task,
            last_message_snippet=last_message[:1000]
        )

    # --- 2. Nós do Grafo (Cognitive Steps) ---

    def _planner_node(self, state: AgentState):
        """Nó de Planejamento: Quebra a intenção do usuário em passos lógicos."""
        self.status_callback("🧠 Analisando e Planejando...")
        messages = state['messages']
        user_input = messages[-1].content if messages else ""
        context_block = self._get_context_block()

        # OTIMIZAÇÃO (Short-Circuit): Se a entrada for trivial, evita gastar tokens/tempo planejando.
        # Isso reduz a latência de "Oi" ou "Obrigado" de ~15s para ~5s.
        trivial_keywords = {"oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "obrigado", "valeu", "tchau", "sair", "ajuda", "help"}
        if len(user_input.split()) < self.TRIVIAL_INPUT_THRESHOLD and any(k in user_input.lower() for k in trivial_keywords):
            return {"plan": ["Responder cordialmente ao usuário"], "current_step": 0, "error": None}

        is_specialized_brain = llm_gateway.is_custom_brain_active()

        prompt = self._build_planner_prompt(context_block, user_input, is_specialized_brain)

        response = llm_gateway.chat(
            [{"role": "user", "content": prompt}], verbose=False, timeout=120, json_mode=True,
        )
        content = response.get("content", "[]") if response else "[]"

        plan = []
        try:
            # 1. Tentativa de Parse Direto (Melhor caso)
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    plan = parsed
                elif isinstance(parsed, dict):
                    # Suporte a envelopes JSON comuns
                    plan = parsed.get("plan") or parsed.get("steps") or parsed.get("actions")
            except json.JSONDecodeError:
                pass

            # 2. Tentativa de Extração via Regex (Se parse direto falhou ou não retornou lista)
            if not plan:
                # Regex Non-Greedy para capturar a primeira lista JSON válida
                json_match = re.search(r"\[.*?\]", content, re.DOTALL)
                if json_match:
                    try:
                        plan = json.loads(json_match.group(0))
                    except:
                        pass

            # 3. Auto-Correção (Se ainda falhar)
            if not plan or not isinstance(plan, list):
                # AUTO-CORREÇÃO: Se o modelo não gerou JSON, pede para ele corrigir.
                self.status_callback("🧠 Corrigindo formato do plano...")
                correction_prompt = f"O texto a seguir não é um JSON válido: '{content}'. Converta-o para uma lista JSON de strings. Responda APENAS com o JSON. Exemplo: [\"Passo 1\"]"
                correction_response = llm_gateway.chat(
                    [{"role": "user", "content": correction_prompt}], verbose=False, timeout=120, json_mode=True,
                )
                content = correction_response.get("content", "[]") if correction_response else "[]"

                json_match = re.search(r"\[.*?\]", content, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group(0))

            if not plan or not isinstance(plan, list):
                raise ValueError("Falha estrutural no planejamento.")

            # Sanitização
            plan = [str(p) for p in plan]

        except Exception as e:
            # Fallback Robusto (Graceful Degradation):
            # Se o planejamento falhar, assume que a solicitação é um passo único.
            # Isso é muito melhor do que retornar um erro técnico para o usuário.
            self.status_callback(f"⚠️ Planejamento complexo falhou. Usando execução direta.")
            plan = [user_input]

        return {"plan": plan, "current_step": 0, "error": None}

    def _executor_node(self, state: AgentState):
        """Nó Executor: Foca em resolver UM passo do plano por vez."""
        plan = state.get('plan', [])
        step_idx = state.get('current_step', 0)

        if step_idx >= len(plan):
            return {"messages": [AIMessage(content="Plano finalizado.")]}

        current_task = plan[step_idx]
        self.status_callback(f"⚙️ Executando passo {step_idx + 1}/{len(plan)}: {current_task}")
        context = state.get('tool_outputs', {})
        context_block = self._get_context_block()

        is_specialized_brain = llm_gateway.is_custom_brain_active()
        previous_error = state.get('error')
        last_msg = state['messages'][-1] if state['messages'] else None
        retry_count = state.get('retry_count', 0)

        prompt = self._build_executor_prompt(
            context_block, step_idx, plan, current_task, context,
            is_specialized_brain, previous_error, retry_count, last_msg
        )

        # Converte histórico LangChain -> Gateway Format
        gateway_msgs = []
        for m in state['messages']:
            role = "user" if isinstance(m, HumanMessage) else "assistant"
            # Sanitização: Garante que content não seja None (comum em mensagens de Tool Call)
            content = m.content if m.content is not None else ""
            gateway_msgs.append({"role": role, "content": content})
        gateway_msgs.append({"role": "user", "content": prompt})

        # Injeta definições de ferramentas do ToolManager
        all_tools = self.tool_manager.tools_definitions
        # OTIMIZAÇÃO: Filtra ferramentas baseadas na tarefa atual para economizar tokens
        tools = self._filter_tools(all_tools, current_task)

        tool_count = len(tools) if tools else 0
        original_count = len(all_tools) if all_tools else 0

        self.status_callback(f"⚙️ Executando passo {step_idx + 1}/{len(plan)}: {current_task} (Enviando {tool_count}/{original_count} ferramentas...)")
        response = llm_gateway.chat(gateway_msgs, tools=tools, verbose=False, timeout=120)

        # TRATAMENTO DE FALHA: Se o gateway falhar (ex: timeout, erro de API), ele retorna None.
        # O nó deve capturar isso e atualizar o estado com um erro para o grafo reagir.
        if not response:
            error_msg = "Falha de comunicação com o provedor de IA. A operação não pode continuar."
            return {
                "messages": [AIMessage(content=f"⛔ Erro: {error_msg}")],
                "error": error_msg,
            }

        # HEURÍSTICA DE RECUPERAÇÃO: Se o modelo respondeu apenas com o nome da ferramenta (texto),
        # convertemos para uma chamada de ferramenta sintética.
        if not response.get("tool_calls") and response.get("content"):
            content = response.get("content", "").strip()
            # Verifica se o conteúdo é exatamente o nome de uma ferramenta disponível
            available_tool_names = {t['function']['name'] for t in tools} if tools else set()

            # 1. Match Exato
            clean_content = content.strip("`'\"")
            found_tool = None

            if clean_content in available_tool_names:
                found_tool = clean_content

            # 2. Match Parcial (Procura nome da ferramenta no texto curto)
            elif len(content) < 300:
                for tool_name in available_tool_names:
                    if tool_name in content:
                        found_tool = tool_name
                        break

            if found_tool:
                response["tool_calls"] = [{
                    "id": f"call_synthetic_{found_tool}",
                    "type": "function",
                    "function": {
                        "name": found_tool,
                        "arguments": "{}" # Assume sem argumentos se não especificado
                    }
                }]

        if response and response.get("tool_calls"):
            # Sinaliza intenção de uso de ferramenta
            return {
                "messages": [AIMessage(content=response.get("content") or "", additional_kwargs={"tool_calls": response["tool_calls"]})]
            }

        return {
            "messages": [AIMessage(content=response.get("content") or "")]
        }

    def _tools_node(self, state: AgentState):
        """Nó de Ferramentas: Ponte para o MCP ToolManager."""
        last_msg = state['messages'][-1]
        tool_calls = last_msg.additional_kwargs.get("tool_calls", [])
        tool_names = [t['function']['name'] for t in tool_calls]
        self.status_callback(f"🛠️ Invocando ferramentas: {', '.join(tool_names)}...")

        outputs = {}
        results_text = []

        for call in tool_calls:
            func = call['function']
            name = func['name']
            try:
                args = json.loads(func['arguments']) if isinstance(func['arguments'], str) else func['arguments']
            except:
                args = {}

            # FIX: Tratamento de erro robusto para evitar que uma ferramenta quebre o grafo
            try:
                # Executa via ToolManager (Requer callbacks mockados por enquanto)
                # Na integração final, passaremos os callbacks reais do ArchitectAgent
                output = self.tool_manager.execute_tool(
                    name,
                    context_resolver=self.context_resolver,
                    audit_logger=self.audit_logger,
                    tool_args=args
                )
            except Exception as e:
                output = f"Error executing tool '{name}': {str(e)}"
                # Registra o erro no audit log para visibilidade
                self.audit_logger(name, "EXEC_ERROR", str(output), status="ERROR")

            outputs[name] = output
            results_text.append(f"Tool '{name}' result: {str(output)[:500]}...")

        new_outputs = state.get('tool_outputs', {}).copy()
        new_outputs.update(outputs)

        return {
            "tool_outputs": new_outputs,
            "messages": [HumanMessage(content="\n".join(results_text))]
        }

    def _critic_node(self, state: AgentState):
        """Nó Crítico: Avalia sucesso e avança o plano usando um modelo 'nano'."""
        plan = state.get('plan', [])
        step_idx = state.get('current_step', 0)
        retry_count = state.get('retry_count', 0)
        MAX_RETRIES = 1 # OTIMIZAÇÃO: Reduzido de 3 para 1 para evitar loops em hardware modesto (Fail-Fast)

        if step_idx >= len(plan):
            # Se já estamos além do último passo, não há o que criticar.
            return {}

        current_task = plan[step_idx]
        self.status_callback(f"🧐 Avaliando resultado de: {current_task}...")
        last_message = state['messages'][-1].content

        prompt = self._build_critic_prompt(current_task, last_message)

        response = llm_gateway.chat(
            [{"role": "user", "content": prompt}],
            verbose=False,
            size="nano", # OTIMIZAÇÃO: Usa modelo leve para avaliação booleana
            timeout=120
        )

        # TRATAMENTO DE FALHA: Se o gateway falhar.
        if not response:
            error_message = "Crítico falhou: Falha de comunicação com o modelo de avaliação."
            # Avança para não ficar em loop, mas registra o erro.
            return {"current_step": state['current_step'] + 1, "error": error_message}

        decision = response.get("content", "FAILURE").strip().upper()

        if "SUCCESS" in decision:
            return {"current_step": state['current_step'] + 1, "error": None, "retry_count": 0}
        else:
            if retry_count < MAX_RETRIES:
                error_message = f"O resultado do passo '{current_task}' não foi satisfatório (Tentativa {retry_count + 1}/{MAX_RETRIES})."
                self.status_callback(f"🔄 Tentando novamente ({retry_count + 1}/{MAX_RETRIES})...")
                # Mantém o passo atual, incrementa retry e define erro para o Executor ver
                return {"retry_count": retry_count + 1, "error": error_message}
            else:
                error_message = f"Crítico falhou no passo: '{current_task}' após {MAX_RETRIES} tentativas. Avançando..."
                return {"current_step": state['current_step'] + 1, "error": error_message, "retry_count": 0}

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("planner", self._planner_node)
        workflow.add_node("executor", self._executor_node)
        workflow.add_node("tools", self._tools_node)
        workflow.add_node("critic", self._critic_node)

        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "executor")

        # Roteamento Condicional
        def router(state):
            last_msg = state['messages'][-1]
            # Se o executor decidiu chamar ferramenta -> vai para tools
            if isinstance(last_msg, AIMessage) and "tool_calls" in last_msg.additional_kwargs:
                return "tools"
            # Se acabou o plano -> Fim
            if state['current_step'] >= len(state['plan']):
                return END
            # Se respondeu texto -> Critic avalia
            return "critic"

        workflow.add_conditional_edges("executor", router, {"tools": "tools", "critic": "critic", END: END})

        # CORREÇÃO: Após executar ferramenta, volta ao executor para interpretar o resultado
        # Antes estava indo para 'critic', o que encerrava o passo retornando o JSON bruto.
        workflow.add_edge("tools", "executor")

        # Loop do Critic
        def plan_check(state):
            if state['current_step'] >= len(state['plan']):
                return END
            return "executor" # Próximo passo

        workflow.add_conditional_edges("critic", plan_check, {"executor": "executor", END: END})

        return workflow.compile(checkpointer=self.memory)