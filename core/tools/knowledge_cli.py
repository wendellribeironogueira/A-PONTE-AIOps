#!/usr/bin/env python3
"""
Knowledge Engineer (Engenheiro de Conhecimento)
-----------------------------------------------
Interface interativa para alimentar o cérebro da IA (aponte-ai).
Permite criar ADRs e Snippets de conhecimento de forma estruturada.

Funcionalidade: Detecta automaticamente o contexto de execução para imports.
"""

import os
import subprocess
import sys
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from core.agents import sentinel as autonomous_agent
from core.lib import utils as common
from core.services import llm_gateway as llm_client
from core.services.knowledge import ingestor as auto_learn
from core.services.knowledge import web_learner


def get_docs_paths():
    root = common.get_project_root()
    docs_root = root / "docs"
    adrs_dir = docs_root / "adrs"
    kb_dir = docs_root / "knowledge_base"

    # Garante estrutura
    adrs_dir.mkdir(parents=True, exist_ok=True)
    kb_dir.mkdir(parents=True, exist_ok=True)

    return adrs_dir, kb_dir


def create_adr():
    adrs_dir, _ = get_docs_paths()

    common.console.rule("[bold cyan]📝 Nova Architecture Decision Record (ADR)[/]")

    # Calcula próximo ID
    existing = list(adrs_dir.glob("*.md"))
    next_id = len(existing) + 1

    title = Prompt.ask("Título da Decisão (ex: Usar DynamoDB para Lock)")
    status = Prompt.ask(
        "Status", choices=["Proposto", "Aceito", "Depreciado"], default="Proposto"
    )
    context = Prompt.ask("Contexto (O problema)")
    decision = Prompt.ask("Decisão (A solução)")
    consequences = Prompt.ask("Consequências (Pros/Contras)")

    filename = f"{next_id:03d}-{title.lower().replace(' ', '-')}.md"
    filepath = adrs_dir / filename

    content = f"""# ADR-{next_id:03d}: {title}

## Status
{status}

## Contexto
{context}

## Decisão
{decision}

## Consequências
{consequences}
"""
    filepath.write_text(content, encoding="utf-8")
    common.log_success(f"ADR criada: {filepath}")
    return True


def add_knowledge_snippet():
    _, kb_dir = get_docs_paths()

    common.console.rule("[bold cyan]🧠 Adicionar Conhecimento Geral[/]")

    title = Prompt.ask("Tópico (ex: Padrao Tags AWS)")
    content = Prompt.ask("Conteúdo/Regra (Pode colar texto longo)")

    filename = f"{title.lower().replace(' ', '_')}.md"
    filepath = kb_dir / filename

    file_content = f"# Conhecimento: {title}\n\n{content}\n"

    filepath.write_text(file_content, encoding="utf-8")
    common.log_success(f"Conhecimento salvo em: {filepath}")
    return True


def run_trainer():
    common.console.rule("[bold magenta]🔄 Re-treinando Cérebro...[/]")
    subprocess.run(["aponte", "ai", "train"])


def import_web_knowledge():
    common.console.rule("[bold cyan]🌐 Injetar Conhecimento da Web[/]")
    url = Prompt.ask("Cole a URL (AWS Docs, Blog Post, Tutorial)")
    title = Prompt.ask(
        "Dê um título curto para este conhecimento (ex: EKS Best Practices)"
    )

    if web_learner.learn_from_web(url, title):
        if Confirm.ask("Deseja treinar o cérebro agora com este novo conhecimento?"):
            run_trainer()


def suggest_sources():
    common.console.rule(
        "[bold cyan]🕵️ Discovery: Sugestão de Fontes (Retroalimentação)[/]"
    )
    topic = Prompt.ask(
        "Sobre qual tema você quer que a IA busque referências? (ex: DynamoDB, EKS Security)"
    )

    prompt = f"""
    Atue como um Engenheiro de Cloud Sênior e Pesquisador.
    Liste 3 a 5 URLs OFICIAIS e ATUALIZADAS de documentação técnica sobre: {topic}.
    Priorize: AWS Documentation, HashiCorp Developer, CNCF, OWASP.
    Responda APENAS com as URLs, uma por linha. Sem texto adicional ou marcadores.
    """

    common.console.print(
        "[dim]🤖 Consultando IA Local (Pode alucinar URLs, verifique antes)...[/dim]"
    )
    response = llm_client.generate(prompt)

    if response and response.startswith("[ERRO]"):
        common.console.print(f"[red]{response}[/]")

    elif response:
        urls = [
            line.strip()
            for line in response.splitlines()
            if line.strip().startswith("http")
        ]
        if urls:
            common.console.print("\n[bold]URLs Encontradas:[/]")
            for u in urls:
                common.console.print(f" - {u}")

            if Confirm.ask(
                "\nDeseja adicionar essas URLs à fila de aprendizado (sources.txt)?"
            ):
                root = common.get_project_root()
                sources_file = root / "docs" / "sources.txt"
                with open(sources_file, "a", encoding="utf-8") as f:
                    f.write(f"\n# === Sugestões IA: {topic} ===\n")
                    for u in urls:
                        f.write(f"{u}\n")
                common.log_success(
                    "URLs adicionadas! Execute a opção [4] para processá-las."
                )
        else:
            common.console.print(
                "[yellow]Nenhuma URL válida encontrada na resposta.[/]"
            )


def run_audit():
    common.console.rule("[bold cyan]🔍 Auditoria de Conformidade (Path Auditor)[/]")
    common.console.print(
        "[dim]Verifica se o projeto segue as ADRs e padrões que a IA aprendeu.[/dim]"
    )

    save = Confirm.ask("Deseja salvar o relatório em docs/audits/?")

    # Localiza o script path_auditor.py
    script_path = common.get_project_root() / "core/tools/path_auditor.py"

    cmd = [sys.executable, str(script_path), "project"]
    if save:
        cmd.append("--save")

    subprocess.run(cmd)
    Prompt.ask("\nPressione Enter para continuar...")


def show_stats():
    common.console.rule("[bold cyan]📊 Estatísticas da Base de Conhecimento[/]")

    root = common.get_project_root()
    adrs = list((root / "docs" / "adrs").glob("*.md"))
    kb = list((root / "docs" / "knowledge_base").glob("*.md"))

    total_chars = 0
    for f in adrs + kb:
        try:
            total_chars += len(f.read_text(encoding="utf-8"))
        except Exception as e:
            common.console.print(f"[dim red]Erro ao ler {f.name}: {e}[/]")

    est_tokens = total_chars // 4

    common.console.print(f"• [bold]ADRs (Decisões):[/] {len(adrs)}")
    common.console.print(f"• [bold]Knowledge Base (Snippets/Web):[/] {len(kb)}")
    common.console.print(f"• [bold]Volume Total:[/] {total_chars:,} caracteres")
    common.console.print(f"• [bold]Estimativa de Tokens:[/] ~{est_tokens:,} tokens")

    if est_tokens > 30000:
        common.console.print(
            "\n[yellow]⚠️  Atenção: O contexto está ficando grande para modelos de 32k.[/yellow]"
        )

    Prompt.ask("\nPressione Enter para continuar...")


def main():
    while True:
        common.console.clear()
        common.console.rule("[bold magenta]👷 A-PONTE Knowledge Engineer[/]")
        common.console.print(
            "[dim]Gerencie o conhecimento que alimenta a IA (aponte-ai)[/dim]\n"
        )

        common.console.print("[1] 📝 Criar nova ADR (Decisão Arquitetural)")
        common.console.print("[2] 🧠 Adicionar Conhecimento/Regra (Snippet)")
        common.console.print("[3] 🌐 Injetar Conhecimento da Web (AWS Docs/Blogs)")
        common.console.print("[4] 🤖 Auto-Learn (Lote via docs/sources.txt)")
        common.console.print("[5] ️ Discovery (IA sugere fontes para aprender)")
        common.console.print("[6] 🚀 Re-treinar Cérebro (Aplicar mudanças)")
        common.console.print("[7] 🔍 Auditar Conformidade (Path Auditor)")
        common.console.print("[8] 🩺 Diagnóstico da Base de Conhecimento")
        common.console.print("[0] Sair")

        choice = Prompt.ask(
            "\nEscolha",
            choices=["1", "2", "3", "4", "5", "6", "7", "8", "0"],
            default="0",
        )

        if choice == "0":
            break
        elif choice == "1":
            if create_adr():
                if Confirm.ask("Deseja treinar o cérebro agora para incluir essa ADR?"):
                    run_trainer()
        elif choice == "2":
            if add_knowledge_snippet():
                if Confirm.ask("Deseja treinar o cérebro agora?"):
                    run_trainer()
        elif choice == "3":
            import_web_knowledge()
        elif choice == "4":
            auto_learn.run_batch_ingestion()
            Prompt.ask("\nPressione Enter para continuar...")
        elif choice == "5":
            suggest_sources()
            Prompt.ask("\nPressione Enter para continuar...")
        elif choice == "6":
            run_trainer()
            Prompt.ask("\nPressione Enter para continuar...")
        elif choice == "7":
            run_audit()
        elif choice == "8":
            show_stats()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSaindo...")
