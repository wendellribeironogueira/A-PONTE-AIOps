#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[3].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.services import llm_gateway
from core.services import ollama
from core.agents import auditor
from core.tools import git_auditor
from core.lib.prompts import PromptLoader

def load_infra_context(verbose=False):
    """
    Carrega o estado atual da infraestrutura (Arquivos .tf) para contexto.
    Usado pelo Architect e pelo Trainer.
    """
    infra_context = []
    root = common.get_project_root()

    # Escaneia diretórios chave de infraestrutura
    scan_dirs = [
        root / "infrastructure" / "bootstrap",
        root / "infrastructure" / "modules",
        root / "projects"
    ]

    # Limite de tamanho para não estourar contexto
    total_chars = 0
    limit_chars = 10000

    for d in scan_dirs:
        if d.exists():
            for f in d.rglob("*.tf"):
                if ".terraform" in str(f) or ".terragrunt-cache" in str(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if total_chars + len(content) < limit_chars:
                        infra_context.append(f"--- {f.relative_to(root)} ---\n{content}")
                        total_chars += len(content)
                except Exception as e:
                    common.console.print(f"[dim yellow]⚠️  Falha ao ler {f.name}: {e}[/dim yellow]")

    return "\n".join(infra_context)

def sanitize_for_modelfile(text):
    """Escapa caracteres especiais para o Modelfile."""
    if not text: return ""
    # Escapa aspas triplas que delimitam o bloco SYSTEM
    return text.replace('"""', '\\"\\"\\"')

def train_model():
    common.console.rule("[bold magenta]🧠 A-PONTE AI Trainer[/]")

    root = common.get_project_root()

    # 1. Coleta de Conhecimento (Knowledge Base)
    knowledge = []

    common.console.print("[dim]📖 Lendo Constituição e ADRs...[/dim]")
    # Constituição
    # OTIMIZAÇÃO (PULL STRATEGY): Removemos a injeção estática. O modelo deve usar 'read_resource'.
    # const_file = root / "docs" / "architecture" / "constitution.md"
    # if const_file.exists():
    #     knowledge.append(f"CONSTITUIÇÃO DO SISTEMA:\n{const_file.read_text(encoding='utf-8')}")

    # ADRs
    # adr_file = root / "docs" / "ADR.md"
    # if adr_file.exists():
    #     knowledge.append(f"DECISÕES ARQUITETURAIS (ADRs):\n{adr_file.read_text(encoding='utf-8')}")

    common.console.print("[dim]🛡️  Incorporando Diretrizes de Segurança (Auditor)...[/dim]")
    knowledge.append(f"DIRETRIZES DE SEGURANÇA:\n{auditor.SECURITY_DIRECTIVE}")

    common.console.print("[dim]📋 Incorporando Contratos de Variáveis (Git Auditor)...[/dim]")
    # OTIMIZAÇÃO (PULL STRATEGY): Contratos devem ser consultados sob demanda.
    # knowledge.append(f"CONTRATO DE VARIÁVEIS:\n{git_auditor.VARIABLE_CONTRACT}")

    # 2. Definição do System Prompt (Modelfile)
    base_model = os.getenv("A_PONTE_BASE_MODEL", ollama.DEFAULT_MODEL)

    # Carrega Identidade e Manual para embutir no modelo (Otimização de Contexto)
    loader = PromptLoader()
    identity_block = loader.load("identity")
    tools_manual = loader.load("tools_manual")

    # VALIDAÇÃO CRÍTICA: Se o prompt estiver vazio, o modelo ficará "lobotomizado"
    if not identity_block or len(identity_block) < 10:
        common.console.print("[bold red]❌ Erro Crítico: 'identity' não foi carregada corretamente. Abortando treino.[/]")
        sys.exit(1)

    common.console.print(f"[dim]ℹ️  Identity Size: {len(identity_block)} chars | Manual Size: {len(tools_manual)} chars[/dim]")

    # Sanitização
    full_knowledge = "\n\n".join(knowledge)
    safe_knowledge = sanitize_for_modelfile(full_knowledge)
    safe_behavior = sanitize_for_modelfile(llm_gateway.APONTE_BEHAVIOR_DEFINITIONS)
    safe_manual = sanitize_for_modelfile(tools_manual)

    system_prompt = f"""
{identity_block}

--- CONHECIMENTO BASE (MEMÓRIA DE LONGO PRAZO) ---
{safe_knowledge}

--- MANUAL TÉCNICO ---
{safe_manual}

--- COMPORTAMENTO ---
{safe_behavior}
"""

    modelfile_content = f"""
FROM {base_model}
SYSTEM \"\"\"
{system_prompt}
\"\"\"
PARAMETER temperature 0.0
PARAMETER num_ctx 4096
"""

    # 3. Criação do Modelfile
    modelfile_path = root / "config" / "ai" / "aponte-ai.modelfile"
    modelfile_path.parent.mkdir(parents=True, exist_ok=True)
    modelfile_path.write_text(modelfile_content, encoding="utf-8")

    common.console.print(f"[green]📄 Modelfile gerado em: {modelfile_path}[/green]")

    # 4. Execução do Treino (Ollama Create)
    common.console.print(f"[bold cyan]🔨 Compilando modelo 'aponte-ai' a partir de: [yellow]{base_model}[/yellow]...[/bold cyan]")

    # Garante que o Ollama está rodando
    if not llm_gateway.is_available():
        common.console.print("[yellow]⏳ Iniciando Ollama...[/yellow]")
        llm_gateway.start_server(force=True)

    try:
        # Pull do base model se necessário
        subprocess.run(["ollama", "pull", base_model], check=False)

        # Create
        subprocess.run(["ollama", "create", "aponte-ai", "-f", str(modelfile_path)], check=True)
        common.console.print("\n[bold green]✅ Treinamento concluído! O modelo 'aponte-ai' está pronto para uso.[/bold green]")
        common.console.print("[dim]👉 Context Window: 4096 tokens. Execute 'aponte architect' para testar.[/dim]")
    except Exception as e:
        common.console.print(f"[bold red]❌ Falha ao criar modelo: {e}[/bold red]")

if __name__ == "__main__":
    train_model()
