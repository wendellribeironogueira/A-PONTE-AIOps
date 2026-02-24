#!/usr/bin/env python3
import importlib
import os
import shlex
import subprocess  # nosec B404 - Used to run CLI commands.
import sys
import time
from datetime import datetime
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Third-party imports
try:
    from rich import box  # pyright: ignore [reportMissingImports]
    from rich.align import Align  # pyright: ignore [reportMissingImports]
    from rich.console import Console  # pyright: ignore [reportMissingImports]
    from rich.layout import Layout  # pyright: ignore [reportMissingImports]
    from rich.panel import Panel  # pyright: ignore [reportMissingImports]
    from rich.prompt import Prompt  # pyright: ignore [reportMissingImports]
    from rich.table import Table  # pyright: ignore [reportMissingImports]
    from rich.text import Text  # pyright: ignore [reportMissingImports]
except ImportError:
    print("❌ Erro: A biblioteca 'rich' não está instalada. Execute: pip install rich")
    sys.exit(1)

# Local application imports
from core.lib import aws  # noqa: E402
from core.lib import utils as common  # noqa: E402

console = Console()

# Cache global para informações estáticas do sistema
_SYSTEM_CACHE = {}


def get_system_status(force_refresh=False):
    """Coleta status do sistema para o painel lateral."""
    global _SYSTEM_CACHE

    # Se não forçar refresh e já tiver cache, usa o cache para dados estáticos
    if not force_refresh and _SYSTEM_CACHE:
        static_data = _SYSTEM_CACHE
    else:
        region = os.getenv("AWS_REGION", "sa-east-1")

        # Garante variáveis de ambiente para o Terraform/Terragrunt
        if "TF_VAR_aws_region" not in os.environ:
            os.environ["TF_VAR_aws_region"] = region

        if "TF_VAR_security_email" not in os.environ:
            os.environ["TF_VAR_security_email"] = os.getenv(
                "SECURITY_EMAIL", "security@aponte.platform"
            )

        try:
            account = aws.get_account_id()
        except Exception:
            account = None

        if not account:
            try:
                # Timeout para evitar travamento da UI
                res = subprocess.run(
                    "aws sts get-caller-identity --query Account --output text".split(),
                    capture_output=True,
                    text=True,
                    timeout=2,
                )  # nosec B603
                account = res.stdout.strip() if res.returncode == 0 else "Desconectado"
            except Exception:
                account = "Desconectado"

        # Injeta no ambiente para que o Terraform/Terragrunt possa ler via get_env()
        if account and account != "Desconectado":
            os.environ["TF_VAR_account_id"] = account

        def get_version(cmd, parser):
            try:
                res = subprocess.run(
                    cmd.split(), capture_output=True, text=True, timeout=1
                )  # nosec B603
                if res.returncode == 0:
                    return parser(res.stdout.strip())
                return "N/A"
            except Exception:
                return "N/A"

        aws_ver = get_version(
            "aws --version",
            lambda x: "v" + x.split("/")[1].split(" ")[0] if "/" in x else x,
        )
        tf_ver = get_version(
            "terraform --version", lambda x: x.split("\n")[0].replace("Terraform ", "")
        )
        go_ver = get_version("go version", lambda x: x.split(" ")[2])

        static_data = {
            "region": region,
            "account": account,
            "aws_cli": aws_ver,
            "terraform": tf_ver,
            "go": go_ver,
        }
        _SYSTEM_CACHE = static_data

    projects_dir = common.get_project_root() / "projects"
    active_projects = 0
    if projects_dir.exists():
        active_projects = len([d for d in projects_dir.iterdir() if d.is_dir()])

    context = common.read_context() or "home"
    repos = []
    if context != "home":
        repos_file = projects_dir / f"{context}.repos"
        if repos_file.exists():
            try:
                with open(repos_file) as f:
                    repos = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
            except Exception as e:
                repos = [f"Erro ao ler .repos: {e}"]

    return {
        **static_data,
        "active_projects": active_projects,
        "context": context,
        "repos": repos,
        "last_update": datetime.now().strftime("%H:%M:%S"),
    }


def make_header():
    art = r"""
      _      ____   ___  _   _ _____ _____
     / \    |  _ \ / _ \| \ | |_   _| ____|
    / _ \   | |_) | | | |  \| | | | |  _|
   / ___ \  |  __/| |_| | |\  | | | | |___
  /_/   \_\ |_|    \___/|_| \_| |_| |_____|
  A Ponte entre GitHub ⇄ AWS  |  Backend • Multi-Tenant • Multi-Analista
    """
    return Panel(
        Align.center(Text(art, style="bold cyan")), box=box.ROUNDED, style="blue"
    )


def make_context_panel():
    context = common.read_context() or "home"
    return Panel(
        Align.center(f"📍 CONTEXTO ATUAL: [bold yellow]{context}[/]"),
        box=box.ROUNDED,
        style="white",
    )


def make_menu_table():
    table = Table.grid(expand=True, padding=(0, 2))
    table.add_column(ratio=1)
    table.add_column(ratio=1)

    # Coluna 1
    col1 = Table.grid(expand=True, padding=(0, 0))

    col1.add_row(
        Panel(
            "[1] Novo Projeto\n[2] Mudar de Projeto\n[4] Add Repo (Vincular)\n[6] Remove Repo\n[G] Git Audit (App/Infra)\n[D] Git Clone\n[U] Git Push (Snapshot)\n[K] Backup State\n[Y] Rollback",
            title="📦 Projetos & Git",
            border_style="blue",
            box=box.ROUNDED,
        )
    )
    col1.add_row(
        Panel(
            "[A] Arquiteto (Chat IA)\n[E] Treinar Cérebro\n[L] Knowledge CLI (Learn)\n[M] Sentinel (Daemon)\n[X] Deploy Core (Bootstrap)\n[O] Observer (Logs/Cost)\n[H] AI Doctor (Heal)\n[DOC] Gerar Documentação\n[W] Ops Pipeline",
            title="🧠 Inteligência & Ops",
            border_style="magenta",
            box=box.ROUNDED,
        )
    )

    # Coluna 2
    col2 = Table.grid(expand=True, padding=(0, 0))

    col2.add_row(
        Panel(
            "[8] TF Plan (Dry-Run)\n[9] Deploy Project\n[10] TF Destroy\n[11] Cost Estimate\n[12] Drift Detect\n[R] Drift Fix (Remediate)",
            title="🚀 Infraestrutura",
            border_style="green",
            box=box.ROUNDED,
        )
    )
    col2.add_row(
        Panel(
            "[S] Security Audit (Full)\n[C] Checkov (IaC)\n[T] Trivy (Vulns)\n[P] Prowler (AWS Compliance)\n[F] TFSec (Static)\n[B] Break Glass (Enable)\n[Q] Break Glass (Disable)",
            title="🛡️ Segurança",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )

    table.add_row(col1, col2)
    return table


def make_status_panel(data):
    content = f"""
🌍 Region: [bold]{data['region']}[/]
🆔 Account: [bold]{data['account']}[/]

✔ AWS CLI: {data['aws_cli']}
✔ Go Lang: {data['go']}
✔ Terraform: {data['terraform']}
"""
    if data.get("context") == "home":
        content += f"\n📦 Projetos Ativos: [bold]{data['active_projects']}[/]"
    elif data.get("repos"):
        content += f"\n🔗 Repos ({len(data['repos'])}):"
        for r in data["repos"][:10]:
            short_name = r.split("/")[-1].replace(".git", "")
            content += f"\n  • {short_name}"
        if len(data["repos"]) > 10:
            content += f"\n  ... (+{len(data['repos'])-10})"
    else:
        content += "\n[dim]Nenhum repositório vinculado[/dim]"

    content += f"\n\nÚltima atualização: {data['last_update']}"
    return Panel(
        content, title="🩺 System Status", border_style="cyan", box=box.ROUNDED
    )


def make_footer():
    return Panel(
        Align.center(
            f"Plataforma desenvolvida por Wendell Ribeiro Nogueira | A-PONTE v2.0 (Definitive) | 📂 {project_root} | 🐍 venv"
        ),
        style="dim white",
        box=box.ROUNDED,
    )


def switch_project_interactive(aponte_bin):
    """Lista projetos e permite seleção interativa antes de chamar a CLI."""
    projects_dir = common.get_project_root() / "projects"
    projects = []
    
    if projects_dir.exists():
        projects = sorted([d.name for d in projects_dir.iterdir() if d.is_dir()])
    
    # Garante que o core 'a-ponte' esteja na lista se existir bootstrap
    if "a-ponte" not in projects and (common.get_project_root() / "infrastructure" / "bootstrap").exists():
        projects.insert(0, "a-ponte")
        
    if not projects:
        console.print("[red]Nenhum projeto encontrado.[/]")
        return

    console.print("\n[bold cyan]Projetos Disponíveis:[/]")
    for idx, p in enumerate(projects, 1):
        console.print(f"[{idx}] {p}")
        
    choice = Prompt.ask("\nSelecione o projeto", default="1")
    
    if choice.isdigit() and 1 <= int(choice) <= len(projects):
        run_command(f"{aponte_bin} project switch {projects[int(choice)-1]}")
    elif choice in projects:
        run_command(f"{aponte_bin} project switch {choice}")
    else:
        console.print("[red]Seleção inválida.[/]")


def run_command(cmd):
    # Comandos de diagnóstico e gestão local não devem ser bloqueados por falta de credenciais
    # Isso evita o deadlock onde não consigo rodar o doctor para corrigir a auth
    bypass_auth = any(
        x in cmd for x in ["doctor", "project switch", "repo", "config", "infra"]
    )

    # Garante que a variável crítica para o Terragrunt esteja presente
    if not bypass_auth and "TF_VAR_account_id" not in os.environ:
        console.print(
            "[yellow]⚠️  Aviso: TF_VAR_account_id não detectada. Tentando recuperar...[/]"
        )
        get_system_status(force_refresh=True)  # Força refresh das credenciais
        # Double Check: Se ainda falhar, avisa o usuário do risco iminente
        if "TF_VAR_account_id" not in os.environ:
            console.print(
                "[bold red]❌ Erro: Não foi possível obter o Account ID. Comandos de infraestrutura falharão.[/]"
            )
            return

    console.print(f"\n[dim]Executando: {cmd}[/dim]")

    try:
        # Use shlex.split to safely parse the command string and avoid shell=True
        # FIX: On Windows, shlex.split(posix=True) consumes backslashes in paths.
        use_posix = sys.platform != "win32"
        args = shlex.split(cmd, posix=use_posix)

        # FIX: shlex em modo non-POSIX (Windows) preserva aspas, o que quebra o subprocess.call
        if not use_posix:
            args = [arg.strip('"') for arg in args]

        exit_code = subprocess.call(
            args
        )  # nosec B603 - Commands are from a trusted, hardcoded dictionary.
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Interrompido pelo usuário.[/]")
        exit_code = 130

    if exit_code != 0:
        if exit_code == 2 and "drift" in cmd:
            console.print(f"\n[bold yellow]⚠️  Drift Detectado (Divergência entre Código e Nuvem)[/]")
        else:
            display_code = exit_code
            console.print(f"\n[bold red]❌ Comando falhou (Exit Code: {display_code})[/]")
        if "doctor" not in cmd and "architect" not in cmd:
            if (
                Prompt.ask(
                    "Deseja invocar o AI Doctor para diagnosticar?",
                    choices=["s", "n"],
                    default="s",
                )
                == "s"
            ):
                subprocess.call(
                    [sys.executable, str(project_root / "core/services/doctor.py")]
                )  # nosec B603

    input("\nPressione Enter para continuar...")


def main():
    # Carrega variáveis do .env para o ambiente do processo
    env_file = project_root / ".env"
    if env_file.exists():
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k not in os.environ:
                            os.environ[k] = v.strip("'").strip('"')
        except Exception as e:
            common.console.print(f"[yellow]⚠️  Falha ao carregar .env: {e}[/]")

    # Fallback: Tenta ler chave do Infracost do config local (~/.config/infracost/credentials.yml)
    if "INFRACOST_API_KEY" not in os.environ:
        try:
            creds_path = Path.home() / ".config" / "infracost" / "credentials.yml"
            if creds_path.exists():
                with open(creds_path) as f:
                    for line in f:
                        if "api_key" in line and ":" in line:
                            os.environ["INFRACOST_API_KEY"] = line.split(":", 1)[
                                1
                            ].strip()
                            break
        except Exception as e:
            common.console.print(
                f"[yellow]⚠️  Falha ao carregar credenciais Infracost: {e}[/]"
            )

    # FIX: Desabilita o Pager da AWS CLI para evitar travamentos em subprocessos (ex: aws s3 ls | less)
    os.environ["AWS_PAGER"] = ""

    # Define caminho absoluto do binário para evitar 'command not found'
    bin_path = project_root / "bin" / "aponte"

    if bin_path.exists():
        aponte = f'"{bin_path}"'
    else:
        # Fallback: Assume PATH se não encontrar o binário no local esperado
        aponte = "aponte"
        console.print(
            f"[yellow]⚠️  Aviso: Binário não encontrado em {bin_path}. Usando PATH.[/]"
        )
        time.sleep(1)

    # FIX: ADR-027 - Tratamento do Estado Neutro (In-Memory Override)
    # Se a CLI injetou 'home' na memória, forçamos o disco para 'home' e limpamos a env var
    # para permitir que o usuário troque de contexto livremente durante a sessão.
    if os.environ.get("TF_VAR_project_name") == "home":
        try:
            # Sincroniza o estado físico (disco) com o lógico (memória)
            # Remove aspas se houver para execução direta via lista
            cmd_bin = aponte.strip('"')
            subprocess.run(
                [cmd_bin, "project", "switch", "home"], capture_output=True, check=False
            )  # nosec B603
            # Remove a trava de memória para que leituras futuras peguem o estado do disco
            del os.environ["TF_VAR_project_name"]
        except Exception as e:
            common.console.print(
                f"[yellow]⚠️  Falha na sincronização de contexto (Home): {e}[/]"
            )

    while True:
        importlib.reload(common)  # Fix: Force reload to clear read_context cache (ADR-027)
        console.clear()

        layout = Layout()
        layout.split(
            Layout(name="header", size=10),
            Layout(name="context", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )

        layout["header"].update(make_header())
        layout["context"].update(make_context_panel())
        layout["footer"].update(make_footer())

        layout["body"].split_row(
            Layout(name="menu", ratio=3), Layout(name="status", ratio=1)
        )

        layout["menu"].update(make_menu_table())
        layout["status"].update(make_status_panel(get_system_status()))

        console.print(layout)

        choice = console.input("👉 Escolha uma opção: ").strip().lower()

        if choice == "0":
            break

        commands = {
            # Projetos & Git
            "1": f"{aponte} project create",
            "2": lambda: switch_project_interactive(aponte),
            "4": f"{aponte} repo add",
            "6": f"{aponte} repo remove",
            "g": f"{aponte} audit git",
            "d": f"{aponte} git clone",
            "u": f"{aponte} git push",
            "k": f"{aponte} project backup",
            "y": f"{aponte} project restore",
            # Infraestrutura
            "8": f"{aponte} tf plan",
            "9": f"{aponte} deploy project",
            "10": f"{aponte} tf destroy",
            "11": "docker exec -it -e INFRACOST_API_KEY mcp-terraform infracost breakdown --path /app",
            "12": f"{aponte} drift detect",
            "r": f"{aponte} drift fix",
            # Segurança
            "s": f"{aponte} audit",
            "c": f"{aponte} security checkov",
            "t": f"{aponte} security trivy",
            "p": f"{aponte} security prowler",
            "f": f"{aponte} security tfsec",
            # Inteligência
            "a": f"{aponte} architect",
            "e": f"{aponte} ai train",
            "l": f'"{sys.executable}" "{project_root}/core/tools/knowledge_cli.py"',
            "m": f"{aponte} sentinel",
            "x": f"{aponte} deploy core",
            "o": f"{aponte} observer",
            "h": f"{aponte} doctor",
            "doc": f'"{sys.executable}" "{project_root}/core/tools/doc_bot.py"',
            "b": f"{aponte} break-glass enable",
            "q": f"{aponte} break-glass disable",
            "w": f"{aponte} ops pipeline",
        }

        if choice in commands:
            action = commands[choice]
            if callable(action):
                action()
            else:
                run_command(action)
        else:
            console.print("[red]Opção inválida![/]")
            time.sleep(0.5)


if __name__ == "__main__":
    main()
