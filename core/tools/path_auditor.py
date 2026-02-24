#!/usr/bin/env python3
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from rich.markdown import Markdown
from rich.panel import Panel

from core.domain import prompts as system_context
from core.lib import utils as common
from core.services import llm_gateway as llm_client
from core.tools import git_auditor  # Reutiliza a lógica de descoberta de repositórios


def validate_variable_contract(path_obj):
    """Verifica deterministicamente se as variáveis obrigatórias do A-PONTE estão declaradas."""
    var_file = path_obj / "variables.tf"
    if not var_file.exists():
        return  # A ausência do arquivo já é alertada em outro ponto

    try:
        content = var_file.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        common.log_warning(f"Falha ao ler variables.tf: {e}")
        return
    required = ["project_name", "resource_name", "app_name", "environment"]
    missing = []

    for var in required:
        if not re.search(r'variable\s*"' + var + r'"', content):
            missing.append(var)

    if missing:
        common.console.print(
            f"[bold red]❌ Contrato A-PONTE violado: Variáveis obrigatórias ausentes em variables.tf: {', '.join(missing)}[/]"
        )
        common.console.print(
            "[dim]Essas variáveis são essenciais para o isolamento multi-tenant e tagging automático.[/dim]"
        )
    else:
        common.console.print("[green]✔ Contrato de Variáveis (A-PONTE) validado.[/]")


def validate_adrs_with_ai(path_obj, tf_files, repo_type="infra", save_report=False):
    common.console.print(
        "[bold magenta]🤖 IA: Analisando conformidade arquitetural (ADRs)...[/]"
    )

    # Coleta contexto leve (lista de arquivos e amostra do main.tf)
    file_structure = "\n".join([f.name for f in tf_files])
    main_tf_content = ""
    main_tf = path_obj / "main.tf"
    if main_tf.exists():
        try:
            full_content = main_tf.read_text(encoding="utf-8", errors="ignore")
            if len(full_content) > 3000:
                # Prioriza o bloco terraform {} (Backend/Providers) para a IA não alucinar que falta
                tf_block_match = re.search(r'(terraform\s*\{.*?\})', full_content, re.DOTALL)
                tf_block = tf_block_match.group(1) if tf_block_match else ""
                main_tf_content = f"{tf_block}\n\n... [TRUNCATED] ...\n\n{full_content[-2000:]}"
            else:
                main_tf_content = full_content
        except Exception as e:
            common.log_warning(f"Falha ao ler main.tf para validação ADR: {e}")

    docs_context = system_context.load_docs_context()
    prompt = f"""
    {system_context.APONTE_CONTEXT}
    {docs_context}
    Atue como um Arquiteto de Software Sênior especialista em AWS.
    Analise a estrutura deste projeto Terraform e o conteúdo do main.tf.
    CONTEXTO: Tipo de Repositório: {repo_type.upper()}

    RESTRIÇÃO: O projeto é exclusivamente AWS. Não considere Azure ou GCP.

    Verifique se ele segue estas diretrizes (ADRs):
    1. Backend configurado (S3/DynamoDB ou Terragrunt)?
    2. Uso de Providers versionados?
    3. Separação clara de responsabilidades (pela lista de arquivos)?

    Arquivos presentes:
    {file_structure}

    Conteúdo do main.tf (Amostra):
    ```hcl
    {main_tf_content}
    ```

    Responda com:
    1. Veredito (Aprovado/Atenção)
    2. Pontos de melhoria baseados nos ADRs do A-PONTE.
    Seja breve e direto.
    """

    if llm_client.is_available():
        try:
            response = llm_client.generate(prompt, verbose=False)
        except Exception as e:
            common.log_warning(f"Falha na validação de ADRs via IA: {e}")
            response = None

        if response:
            common.console.print(
                Panel(
                    Markdown(response),
                    title="🧠 Relatório de Conformidade (IA)",
                    border_style="cyan",
                )
            )

            if save_report:
                report_dir = common.get_project_root() / "logs" / "audits"
                report_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"audit_{path_obj.name}_{timestamp}.md"
                file_path = report_dir / filename

                report_content = f"# Relatório de Auditoria: {path_obj.name}\n"
                report_content += f"**Data:** {timestamp}\n"
                report_content += f"**Tipo:** {repo_type}\n\n"
                report_content += "## Análise da IA\n\n"
                report_content += response

                file_path.write_text(report_content, encoding="utf-8")
                common.console.print(f"[dim]📄 Relatório salvo em: {file_path}[/dim]")
    else:
        common.console.print(
            "[yellow]⚠️  IA não disponível para validação avançada.[/]"
        )


def audit_path(target_path, mode, repo_type="infra", save_report=False):
    common.console.print(
        f"[bold cyan]🔍 Auditando caminho: {target_path} (Modo: {mode}, Tipo: {repo_type})[/]"
    )

    path_obj = Path(target_path)
    if not path_obj.exists():
        common.log_error(f"Caminho não encontrado: {target_path}")
        sys.exit(1)

    # Gera estrutura para contexto da IA
    repo_structure = ""
    try:
        files = []
        for p in path_obj.rglob("*"):
            if p.is_file() and not git_auditor.is_excluded(p):
                files.append(str(p.relative_to(path_obj)))
        repo_structure = "\n".join(sorted(files)[:200])
    except Exception as e:
        common.log_warning(f"Falha ao gerar estrutura do repositório: {e}")

    # Verificações básicas de estrutura
    required_files = ["README.md", ".gitignore"]
    missing = []
    for f in required_files:
        if (path_obj / f).exists():
            continue
        # Se estiver auditando a pasta 'terraform', aceita se o arquivo estiver na raiz do projeto
        if path_obj.name == "infrastructure" and (path_obj.parent / f).exists():
            continue
        missing.append(f)

    if missing:
        common.console.print(
            f"[yellow]⚠️  Arquivos padrão ausentes: {', '.join(missing)}[/]"
        )
    else:
        common.console.print("[green]✔ Estrutura base (README/Gitignore) validada.[/]")

    # Validação Específica de APP
    if repo_type == "app":
        app_files = [
            "Dockerfile",
            "package.json",
            "requirements.txt",
            "go.mod",
            "pom.xml",
        ]
        found_app = [f for f in app_files if (path_obj / f).exists()]
        if found_app:
            common.console.print(
                f"[blue]ℹ️  Arquivos de Aplicação detectados: {', '.join(found_app)}[/]"
            )

    # Validação de Arquivos de Configuração (YAML)
    # Garante que pipelines e configs (até os .yml) sejam validados pela IA
    yaml_files = list(path_obj.glob("**/*.yml")) + list(path_obj.glob("**/*.yaml"))
    yaml_files = [f for f in yaml_files if not git_auditor.is_excluded(f)]

    if yaml_files:
        common.console.print(
            f"[bold magenta]🔍 Analisando {len(yaml_files)} arquivos de configuração (YAML)...[/]"
        )
        for f in yaml_files:
            git_auditor.analyze_alignment(
                f,
                "Configuração YAML",
                path_obj.name,
                repo_type,
                mode,
                repo_structure=repo_structure,
                root_path=path_obj,
            )

    # Análise Terraform
    tf_files = list(path_obj.glob("*.tf"))
    if tf_files:
        common.console.print(
            f"[blue]ℹ️  Projeto Terraform detectado ({len(tf_files)} arquivos).[/]"
        )

        # Check de arquivos padrão do Terraform
        tf_standards = ["main.tf", "variables.tf", "outputs.tf", "versions.tf"]
        missing_tf = [f for f in tf_standards if not (path_obj / f).exists()]

        if missing_tf:
            common.console.print(
                f"[yellow]⚠️  Arquivos Terraform recomendados ausentes: {', '.join(missing_tf)}[/]"
            )
        else:
            common.console.print("[green]✔ Estrutura Terraform padrão completa.[/]")

        # Validação de Contrato de Variáveis (Determinístico)
        validate_variable_contract(path_obj)

        # Validação de ADRs com IA
        validate_adrs_with_ai(path_obj, tf_files, repo_type, save_report)


def main():
    parser = argparse.ArgumentParser(description="Auditor de Caminho Local")
    parser.add_argument(
        "path",
        nargs="?",
        default="project",
        help="Caminho ou 'project' para o contexto atual (Default: project)",
    )
    parser.add_argument("--mode", default="default", help="Modo de execução")
    parser.add_argument(
        "--type", default="infra", help="Tipo do repositório (app/infra)"
    )
    parser.add_argument(
        "--save", action="store_true", help="Salva o relatório da IA em docs/audits/"
    )

    args, unknown = parser.parse_known_args()

    target_path = args.path
    if target_path == "project":
        # Modo Inteligente: Itera sobre repositórios vinculados (App -> Infra)
        project_name = common.read_context()
        if project_name == "home":
            common.log_error("Modo projeto requer um contexto ativo.")
            return

        # Reutiliza a inteligência do git_auditor para obter a lista ordenada e tipada
        repos = git_auditor.get_linked_repos(project_name)
        root = common.get_project_root()

        for repo_full_name, r_type in repos:
            repo_short = repo_full_name.split("/")[-1]
            # Assume que os repos estão na mesma pasta pai do projeto A-PONTE (irmãos)
            repo_path = root.parent / repo_short
            if repo_path.exists():
                audit_path(repo_path, args.mode, r_type, args.save)
            else:
                common.console.print(
                    f"[yellow]⚠️  Repo local não encontrado: {repo_path} (Esperado: {r_type})[/]"
                )
        return

    audit_path(target_path, args.mode, args.type, args.save)


if __name__ == "__main__":
    main()
