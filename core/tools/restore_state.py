#!/usr/bin/env python3
import sys
import os
import subprocess
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common

console = Console()

def get_backups(project_name):
    """Lista backups de estado disponíveis."""
    backup_root = common.get_project_root() / ".aponte-versions" / "states" / project_name
    if not backup_root.exists():
        return []

    backups = []
    for d in backup_root.iterdir():
        if d.is_dir() and (d / "terraform.tfstate").exists():
            backups.append(d.name)

    return sorted(backups, reverse=True)

def restore_state(project_name, version_id):
    """Restaura o estado remoto a partir de um backup local."""
    root = common.get_project_root()
    backup_file = root / ".aponte-versions" / "states" / project_name / version_id / "terraform.tfstate"

    if not backup_file.exists():
        common.log_error(f"Arquivo de estado não encontrado: {backup_file}")
        return False

    # Define diretório do Terraform (Bootstrap ou Projeto)
    if project_name == "a-ponte":
        tf_dir = root / "infrastructure" / "bootstrap"
    else:
        tf_dir = root / "projects" / project_name

    if not tf_dir.exists():
        common.log_error(f"Diretório do projeto não encontrado: {tf_dir}")
        return False

    common.console.print(f"\n[bold red]⚠️  PERIGO: Você está prestes a sobrescrever o estado remoto na AWS![/]")
    common.console.print(f"Projeto: [cyan]{project_name}[/]")
    common.console.print(f"Versão: [cyan]{version_id}[/]")
    common.console.print(f"Origem: {backup_file}")

    if not Confirm.ask("Tem certeza absoluta que deseja fazer o PUSH deste estado?"):
        common.console.print("Operação cancelada.")
        return False

    # Caminhos relativos para o container Docker
    try:
        rel_backup_path = backup_file.relative_to(root)
        rel_tf_dir = tf_dir.relative_to(root)
    except ValueError:
        common.log_error("Caminhos fora da raiz do projeto não suportados.")
        return False

    container_backup_path = f"/app/{rel_backup_path}"
    container_tf_dir = f"/app/{rel_tf_dir}"

    common.console.print("[dim]Executando 'terragrunt state push' via Docker (mcp-terraform)...[/dim]")

    # Comando para executar dentro do container
    # Usa -force para sobrescrever o estado remoto (necessário para rollback)
    docker_cmd = [
        "docker", "exec",
        "-w", container_tf_dir,
        "-i", "mcp-terraform",
        "terragrunt", "state", "push", "-force", container_backup_path
    ]

    try:
        # Executa o comando
        result = subprocess.run(docker_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            common.log_success("Estado restaurado com sucesso!")
            common.console.print(result.stdout)
            return True
        else:
            common.log_error("Falha ao restaurar estado.")
            common.console.print(f"[red]{result.stderr}[/]")
            common.console.print(f"[dim]{result.stdout}[/dim]")
            return False

    except Exception as e:
        common.log_error(f"Erro na execução: {e}")
        return False

def main():
    common.console.rule("[bold magenta]🚑 A-PONTE State Restorer[/]")

    project = os.getenv("TF_VAR_project_name") or common.read_context()
    if project == "home":
        project = Prompt.ask("Qual projeto deseja restaurar?")

    backups = get_backups(project)

    if not backups:
        common.console.print(f"[yellow]Nenhum backup de estado encontrado para '{project}'.[/]")
        common.console.print("[dim]Dica: Backups são criados automaticamente ao rodar 'aponte project destroy'.[/dim]")
        return

    table = Table(title=f"Backups Disponíveis: {project}")
    table.add_column("ID (Timestamp)", style="cyan")

    for b in backups:
        table.add_row(b)

    common.console.print(table)

    version = Prompt.ask("Digite o ID da versão para restaurar (ou Ctrl+C para sair)")

    if version in backups:
        restore_state(project, version)
    else:
        common.console.print("[red]Versão inválida.[/]")

if __name__ == "__main__":
    main()
