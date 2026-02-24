#!/usr/bin/env python3
import sys
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common
from core.services import llm_gateway

def main():
    common.console.rule("[bold blue]📝 A-PONTE DocBot[/]")

    project_name = common.read_context()
    if project_name == "home":
        common.log_error("Selecione um projeto para gerar documentação.")
        sys.exit(1)

    project_dir = common.get_project_root() / "projects" / project_name
    if not project_dir.exists():
        common.log_error(f"Diretório do projeto não encontrado: {project_dir}")
        sys.exit(1)

    common.console.print(f"[dim]Analisando projeto: {project_name}...[/dim]")

    # Coleta estrutura
    files = [f.name for f in project_dir.iterdir()]

    prompt = f"""
    Atue como um Technical Writer.
    Gere um arquivo README.md profissional para o projeto '{project_name}'.

    Arquivos detectados na raiz: {', '.join(files)}

    O README deve conter:
    1. Título e Descrição (Assuma que é um projeto na plataforma A-PONTE AWS).
    2. Estrutura de Pastas.
    3. Como Rodar (Use comandos 'aponte' ou 'terragrunt').
    4. Se houver 'Dockerfile', explique como buildar.
    5. Se houver arquivos .tf, mencione a infraestrutura.

    Responda apenas com o conteúdo Markdown.
    """

    readme_content = llm_gateway.generate(prompt, verbose=True)

    if readme_content:
        readme_path = project_dir / "README.md"
        # Remove code blocks se a IA colocou
        readme_content = readme_content.replace("```markdown", "").replace("```", "")

        readme_path.write_text(readme_content.strip(), encoding="utf-8")
        common.log_success(f"Documentação gerada em: {readme_path}")
    else:
        common.log_error("Falha ao gerar documentação via IA.")

if __name__ == "__main__":
    main()
