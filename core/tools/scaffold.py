#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

try:
    from cookiecutter.main import cookiecutter
except ImportError:
    print("❌ Erro: Cookiecutter não instalado. Execute: pip install cookiecutter")
    sys.exit(1)

# Adiciona raiz ao path para imports do core
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from rich.console import Console

console = Console()


def main():
    # Parse manual de argumentos key=value (ex: name=projeto)
    args = sys.argv[1:]
    context = {}
    json_file = None

    for arg in args:
        if arg.startswith("--load-json="):
            json_file = arg.split("=", 1)[1]
        elif "=" in arg:
            key, value = arg.split("=", 1)
            context[key] = value

    # Carrega contexto do JSON se fornecido (Integração com Git Auditor)
    if json_file:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                json_context = json.load(f)
                context = {**json_context, **context}  # CLI override
        except Exception as e:
            console.print(f"[bold red]❌ Erro ao carregar JSON: {e}[/]")
            sys.exit(1)

    # Normalização e Validação do Contrato A-PONTE
    if "name" in context and "project_name" not in context:
        context["project_name"] = context["name"]

    # SAFETY: Sanitiza nome do projeto para evitar path traversal ou caracteres inválidos
    if "project_name" in context:
        try:
            context["project_name"] = common.normalize_project_name(context["project_name"])
        except AttributeError:
            # Fallback se common não tiver a função (Defesa em profundidade)
            import re
            context["project_name"] = re.sub(r"[^a-z0-9-]", "-", context["project_name"].lower()).strip("-")

    required = ["project_name", "environment", "app_name", "resource_name", "aws_region"]
    missing = [v for v in required if v not in context]

    if missing:
        console.print(f"[bold red]❌ Erro: Variáveis obrigatórias ausentes: {', '.join(missing)}[/]")
        console.print(
            "👉 Uso: aponte project scaffold -- name=... environment=... app_name=... resource_name=... aws_region=..."
        )
        sys.exit(1)

    project_name = context["project_name"]
    root_dir = common.get_project_root()
    projects_dir = root_dir / "projects"

    # Define local do template (Padrão A-PONTE)
    template_path = root_dir / "templates" / "project-template"

    if not template_path.exists():
        console.print(
            f"[yellow]⚠️  Template local não encontrado em: {template_path}[/]"
        )
        console.print(
            "[red]❌ Falha: Diretório de template 'templates/project-template' não existe.[/]"
        )
        console.print(
            "[dim]Dica: Crie o diretório do template ou configure um repositório git remoto.[/dim]"
        )
        sys.exit(1)

    console.print(
        f"[bold cyan]🚀 Gerando projeto '{project_name}' via Cookiecutter...[/]"
    )

    extra_context = {
        "project_name": project_name,
        "project_slug": project_name,
        **context,
    }

    try:
        cookiecutter(
            str(template_path),
            no_input=True,
            extra_context=extra_context,
            output_dir=str(projects_dir),
            overwrite_if_exists=True,
        )
        console.print(
            f"[bold green]✅ Projeto '{project_name}' criado com sucesso em projects/{project_name}![/]"
        )
    except Exception as e:
        console.print(f"[bold red]❌ Erro no Cookiecutter: {e}[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
