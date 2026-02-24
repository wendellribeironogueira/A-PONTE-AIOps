# Centralized Prompt Definitions and Linguistic Assets

# --- Linguistic Assets ---
TOOL_FILTER_TRANSLATIONS = {
    "listar": "list", "lista": "list", "ver": "get", "ler": "read", "criar": "create",
    "apagar": "delete", "remover": "delete", "atualizar": "update",
    "executar": "run", "rodar": "run", "checar": "check", "verificar": "check",
    "buscar": "lookup", "procurar": "lookup"
}

TOOL_FILTER_COMMON_VERBS = {"list", "get", "check", "run", "create", "delete", "update", "read"}

# Lista negra de alucinações de sintaxe HCL comuns em modelos menores (DeepSeek 1.5b/Qwen)
HCL_HALLUCINATIONS = [
    "allowVisibility",
    "explicit =",
    "allowed740",
    "validation = only",
    'cli "ami',
    "namespace =",
    "container_content =",
    "role:rds",
    "autenticação_integridade",
    "constraint rule:",
    "force(merge",
    "...",
]

# --- Prompt Templates ---

PLANNER_SPECIALIZED = """
{context_block}
Analise a solicitação do usuário: "{user_input}"
Crie um plano de execução passo-a-passo.
Retorne APENAS uma lista JSON de strings.
"""

PLANNER_GENERIC = """
{context_block}
Você é um Arquiteto de Soluções Sênior (DevOps).
Analise a solicitação do usuário: "{user_input}"

Crie um plano de execução passo-a-passo conciso para atender a solicitação.
Se for uma pergunta simples, crie um plano de 1 passo: "Responder usuário".

Retorne APENAS uma lista JSON de strings.
Exemplo: ["Listar buckets S3", "Verificar logs", "Gerar relatório"]
"""

EXECUTOR_DIRECTIVES_SPECIALIZED = """
DIRETRIZ DE REALIDADE (GROUNDING):
O CONTEXTO ACUMULADO acima é a Verdade Absoluta.
- Se o JSON estiver vazio (`[]` ou `{}`), sua tarefa é informar que nada foi encontrado.
- É ESTRITAMENTE PROIBIDO inventar resultados se eles não estiverem no contexto.
"""

EXECUTOR_DIRECTIVES_GENERIC = """
DIRETRIZ DE EXECUÇÃO (TOOL-FIRST):
Sua função é EXECUTAR tarefas, não explicar como fazê-las.
- Se uma ferramenta disponível pode realizar a tarefa, VOCÊ DEVE usar a ferramenta.
- É PROIBIDO responder com tutoriais ou comandos de shell (aws, git, etc.).

DIRETRIZ DE REALIDADE (GROUNDING):
O CONTEXTO ACUMULADO acima é a Verdade Absoluta.
- Se o JSON estiver vazio (`[]` ou `{}`), sua tarefa é informar que nada foi encontrado.
- É ESTRITAMENTE PROIBIDO inventar resultados se eles não estiverem no contexto.
"""

EXECUTOR_BASE = """{context_block}
{prompt_directives}

PASSO ATUAL ({step_idx}/{total_steps}): {current_task}
CONTEXTO ACUMULADO: {context_json}

Execute o passo atual. Se necessário, use as ferramentas disponíveis."""

CRITIC_BASE = """
Você é um avaliador de tarefas (Critic).
A tarefa era: "{current_task}"
O resultado foi: "{last_message_snippet}"

A tarefa foi concluída com sucesso?
Responda APENAS com 'SUCCESS' ou 'FAILURE'.
"""