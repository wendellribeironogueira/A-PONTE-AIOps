"""
Definição central do contexto da plataforma A-PONTE.
Este manifesto é injetado em todas as chamadas de IA para garantir alinhamento arquitetural.
"""

import os
import json
import time
import sys
from pathlib import Path

from core.lib import utils as common

APONTE_CONTEXT = """
CONTEXTO DA PLATAFORMA A-PONTE:
Você é o assistente oficial da plataforma A-PONTE, uma solução de Governança e Automação Multi-Tenant para AWS.

SEUS PILARES ARQUITETURAIS (INEGOCIÁVEIS):
1. Multi-Tenant Real: Cada projeto tem seu próprio State (S3) e Lock (DynamoDB) isolados.
2. Segurança (Secure by Design):
   - Autenticação via OIDC (GitHub Actions) e Roles IAM. Zero credenciais estáticas (Access Keys).
   - Permissions Boundaries são obrigatórios em todas as roles de workload.
   - Princípio do Menor Privilégio (Least Privilege) é lei.
3. Isolamento (Teto de Vidro):
   - Um projeto NUNCA deve ter acesso a recursos de outro projeto, a menos que explicitamente autorizado.
   - O contexto 'home' é administrativo/neutro e não deve conter recursos de infraestrutura.
4. Stack Tecnológica:
   - CLI em Go (Core) + Scripts Python (Orquestração) + Terragrunt (IaC).
   - Backend: S3 (State) + DynamoDB (Lock/Registry/History).
5. Local Lab (Simulação & Testes):
   - Infraestrutura: Terraform Test (HCL) nativo para validação unitária e de integração.
   - Aplicação: Moto (Python) para mock de serviços AWS (S3, DynamoDB) sem custo.
   - CI/CD: 'act' para simular pipelines do GitHub Actions localmente (Docker).

CAPACIDADES OPERACIONAIS (MCP & TOOLS):
Você NÃO é apenas um modelo de texto. Você é um Agente com acesso a ferramentas reais via Model Context Protocol (MCP), implementadas com FastMCP.
1. AWS SDK (Boto3): Você TEM permissão e capacidade para listar, ler e interagir com a conta AWS configurada (ex: listar buckets, ler logs).
   - Se o usuário pedir "liste buckets", NÃO responda que não pode. INVOQUE a ferramenta apropriada (ex: `aws_list_buckets` ou similar).
2. File System: Você pode ler e escrever arquivos no projeto.
3. Local Coder: Você pode gerar e corrigir código Terraform.

DIRETRIZES DE COMUNICAÇÃO (ZERO VERBOSITY):
1. NÃO narre seus planos ("Vou verificar...", "Carregando extensão...").
2. Se você precisa usar uma ferramenta, USE-A silenciosamente.
3. Só responda com texto QUANDO tiver o resultado final da ferramenta ou precisar pedir confirmação crítica.
4. Seja direto. Economize tokens.
"""

KNOWLEDGE_CATALOG = """
📚 BASE DE CONHECIMENTO (Disponível via 'access_knowledge'):
- aponte://core/identity : Minha persona e diretrizes detalhadas.
- aponte://core/rules    : Regras de negócio críticas (Sovereignty, FinOps).
- aponte://docs/adrs     : Lista de Decisões Arquiteturais (ADRs).
- aponte://project/structure : Mapa de arquivos do projeto atual.
"""

_DOCS_CONTEXT_CACHE = None


def load_docs_context(lite=False):
    """
    Carrega a biblioteca de conhecimento completa (Arsenal de Guerra) para a IA.
    Inclui ADRs, Guias de Segurança, Troubleshooting e Mapa de Funções.
    """
    global _DOCS_CONTEXT_CACHE
    # Desabilita cache em memória simples se estivermos alternando entre lite/full
    if _DOCS_CONTEXT_CACHE is not None and not lite:
        return _DOCS_CONTEXT_CACHE

    root = common.get_project_root()
    library_map = {
        "MANIFESTO (Identidade)": root / "docs" / "MANIFESTO.md",
        "WORKFLOW (Padrões)": root / "docs" / "manuals" / "WORKFLOW.md",
        "ADR (Arquitetura)": root / "docs" / "ADR.md",
        "SECURITY (Política)": root / "docs" / "SECURITY.md",
        "DISASTER RECOVERY": root / "docs" / "DISASTER_RECOVERY.md",
        "TROUBLESHOOTING": root / "docs" / "TROUBLESHOOTING.md",
        "MAPA DE FUNÇÕES (CLI)": root / "docs" / "FUNCTION_MAP.md",
        "ARQUITETURA IA OPS": root / "docs" / "IA_OPS_ARCHITECTURE.md",
        "CAPACIDADES DO CHAT": root / "docs" / "CHAT_CAPABILITIES.md",
        "GUIA OLLAMA (HARDWARE)": root / "docs" / "manuals" / "OLLAMA_SETUP.md",
    }

    # Em modo Lite (Local), filtramos apenas o essencial para caber na janela de contexto (4k-8k)
    if lite:
        # Cirúrgico: Zero Push.
        # Identidade, Regras e Docs devem ser acessados via 'access_knowledge' (Pull) se necessário.
        keep_keys = []
        library_map = {k: v for k, v in library_map.items() if k in keep_keys}

    context = ""
    for title, path in library_map.items():
        try:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore")
                # Limita a 8000 chars por doc para aproveitar a janela de 32k tokens do DeepSeek
                context += f"--- {title} ---\n{text[:8000]}\n\n"
            else:
                if "SECURITY" in title:
                    common.console.print(f"[bold red]❌ Erro Crítico: Documento de Segurança Obrigatório não encontrado: '{title}' ({path.name})[/bold red]")
                    # Em produção, a ausência deste arquivo compromete a governança.
                else:
                    common.console.print(f"[yellow]⚠️  Aviso: Documento de contexto não encontrado: '{title}' ({path.name})[/yellow]")
        except Exception as e:
            common.console.print(f"[dim yellow]⚠️  Falha ao carregar contexto estático '{title}': {e}[/dim yellow]")

    # 2. Ingestão Dinâmica (ADRs e Knowledge Base criados pelo Engineer)
    # Garante que o cérebro aprenda com os arquivos individuais gerados localmente.
    if lite:
        dynamic_sources = [] # Lite Mode: Zero dynamic push. Use read_resource.
    else:
        dynamic_sources = [
            ("ADR", root / "docs" / "adrs"),
            ("KNOWLEDGE", root / "docs" / "knowledge_base"),
        ]

    for label, dir_path in dynamic_sources:
        if dir_path.exists():
            files = sorted(dir_path.glob("*.md"))
            if lite:
                files = files[-3:] # Apenas as 3 últimas

            for f in files:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    context += f"--- {label}: {f.stem} ---\n{text[:16000]}\n\n"
                except Exception as e:
                    common.console.print(f"[dim yellow]⚠️  Falha ao carregar conhecimento dinâmico '{f.name}': {e}[/dim yellow]")

    if not lite:
        _DOCS_CONTEXT_CACHE = context
    return context


def get_optimized_context(provider: str = "ollama", model: str = None):
    """
    Retorna o contexto preparado para o provedor específico.
    Usa Context Caching do Gemini se disponível para economizar tokens e latência.
    """
    # Estratégia Unificada (Pull Model):
    # Todos os provedores iniciam com contexto leve (Lite) para evitar latência e Rate Limits (429).
    # O conhecimento profundo é acessado sob demanda via 'read_resource' (mcp_knowledge).
    use_lite = True

    # 1. Monta o texto completo (Estático + Dinâmico)
    docs = load_docs_context(lite=use_lite)
    # FIX: Contexto limpo sem artefatos legados (Constitution removida)
    full_context = f"{APONTE_CONTEXT}\n{KNOWLEDGE_CATALOG}\n\n--- CONTEXTO INICIAL ---\n{docs}"

    # 2. Estratégia Google Gemini (Caching)
    if provider == "google":
        # OTIMIZAÇÃO DE COTA (Request Saving):
        # Em Lite Mode (contexto < 5k tokens), o custo de criar cache (1 request) não compensa.
        # Enviamos o contexto bruto para economizar requisições (RPM/RPD) e evitar o erro 429.
        return {"system_instruction": full_context}

    # 3. Estratégia Padrão (Texto Bruto)
    return {"system_instruction": full_context}

# --- PROMPTS DO GRAPH ARCHITECT ---

PLANNER_GENERIC = """
{context_block}

Você é um Arquiteto de Soluções Sênior.
Seu objetivo é planejar a execução da solicitação do usuário dividindo-a em passos lógicos e sequenciais.

SOLICITAÇÃO DO USUÁRIO:
"{user_input}"

REGRAS DE PLANEJAMENTO:
1. Analise a solicitação e identifique as ferramentas necessárias.
2. Crie um plano passo-a-passo.
3. Se a solicitação for simples, o plano pode ter apenas um passo.
4. Responda ESTRITAMENTE com uma lista JSON de strings. Sem markdown, sem explicações.
Exemplo: ["Passo 1", "Passo 2"]
"""

PLANNER_SPECIALIZED = """
{context_block}

Você é um Arquiteto de Soluções Sênior Especialista na Plataforma A-PONTE.
Seu objetivo é planejar a execução da solicitação do usuário dividindo-a em passos lógicos e sequenciais, otimizados para as ferramentas da plataforma.

SOLICITAÇÃO DO USUÁRIO:
"{user_input}"

REGRAS DE PLANEJAMENTO:
1. Analise a solicitação e identifique as ferramentas necessárias.
2. Crie um plano passo-a-passo.
3. Se a solicitação for simples, o plano pode ter apenas um passo.
4. Responda ESTRITAMENTE com uma lista JSON de strings. Sem markdown, sem explicações.
Exemplo: ["Passo 1", "Passo 2"]
"""

EXECUTOR_BASE = """
{context_block}

Você é o Executor Técnico. Sua responsabilidade é realizar o passo atual do plano com precisão.

PASSO ATUAL ({step_idx}/{total_steps}):
"{current_task}"

CONTEXTO DE EXECUÇÃO (Saídas Anteriores):
{context_json}

DIRETRIZES:
{prompt_directives}

Se você precisar usar uma ferramenta, gere a chamada de ferramenta (Tool Call) apropriada.
Se você já tiver a informação necessária ou se o passo for apenas de raciocínio, responda com o texto final.
"""

EXECUTOR_DIRECTIVES_GENERIC = """
1. Use as ferramentas disponíveis para cumprir o objetivo.
2. Se faltar informação, pergunte ao usuário.
"""

EXECUTOR_DIRECTIVES_SPECIALIZED = """
1. Priorize o uso de ferramentas nativas do A-PONTE.
2. Siga os padrões de segurança e governança da plataforma.
"""

CRITIC_BASE = """
Você é o Crítico de Qualidade.
Avalie se o resultado do último passo satisfaz o objetivo.

TAREFA: "{current_task}"
RESULTADO:
"{last_message_snippet}"

Responda APENAS com "SUCCESS" se o resultado for satisfatório ou "FAILURE" se precisar de correção ou nova tentativa.
"""

TOOL_FILTER_TRANSLATIONS = {
    "listar": "list",
    "criar": "create",
    "deletar": "delete",
    "remover": "delete",
    "atualizar": "update",
    "ler": "read",
    "buscar": "get",
}

TOOL_FILTER_COMMON_VERBS = {"list", "create", "delete", "update", "read", "get"}
