import logging
import functools
import os
import re
import subprocess
import sys
from pathlib import Path

# Usando 'rich' para logging colorido
from rich.console import Console

# Fix para Windows: Força encoding UTF-8 no terminal para suportar emojis
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console()


def get_project_root() -> Path:
    """Encontra o diretório raiz do projeto A-PONTE."""
    # Prioriza a variável de ambiente definida pelo wrapper da CLI Go (aponte install)
    if env_root := os.getenv("APONTE_ROOT"):
        return Path(env_root).resolve()

    # Ajuste para core/lib/utils.py -> Raiz é 3 níveis acima (core/lib/utils.py -> core/lib -> core -> root)
    return Path(__file__).parents[2].resolve()


class ContextFilter(logging.Filter):
    """Filtro para injetar o contexto do projeto nos logs."""

    def filter(self, record):
        record.project_context = read_context()
        return True


def _get_context_file_path(root: Path) -> Path:
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "default"
    session = os.environ.get("APONTE_SESSION_ID", "default")
    # Alinhamento com CLI Go (ADR-027): .aponte/sessions/<user>.<session>
    return root / ".aponte" / "sessions" / f"{user}.{session}"


# Cache global para evitar I/O de disco a cada linha de log
_CACHED_CONTEXT = None

def read_context() -> str:
    """
    SINGLE SOURCE OF TRUTH (SSOT) para ler o contexto do projeto.
    Prioridade: ENV > .aponte/sessions/<user>.<session> > 'home'
    """
    global _CACHED_CONTEXT

    # 1. Prioridade Máxima: Variável de Ambiente
    env_context = os.getenv("TF_VAR_project_name")
    if env_context:
        _CACHED_CONTEXT = env_context.strip()
        return env_context.strip()

    if _CACHED_CONTEXT:
        return _CACHED_CONTEXT

    root = get_project_root()
    context_file = _get_context_file_path(root)

    # 2. Fonte de Verdade Persistente
    if context_file.exists():
        try:
            content = context_file.read_text(encoding="utf-8").strip()
            if content:
                _CACHED_CONTEXT = content
                return content
        except Exception as e:
            console.print(
                f"[red]Erro ao ler o arquivo de contexto '{context_file}': {e}[/red]"
            )

    # 3. Fallback Padrão
    _CACHED_CONTEXT = "home"
    return "home"


def write_context(project_name: str):
    """Escreve o contexto no arquivo de sessão oficial em .aponte/sessions/."""
    global _CACHED_CONTEXT
    root = get_project_root()
    context_file = _get_context_file_path(root)
    try:
        project_name = project_name.strip()
        if not project_name:
            project_name = "home"

        # Sincroniza a memória do processo atual para refletir a mudança imediatamente,
        # sobrescrevendo qualquer valor injetado (ex: "home").
        os.environ["TF_VAR_project_name"] = project_name
        _CACHED_CONTEXT = project_name

        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_file.write_text(project_name, encoding="utf-8")
    except Exception as e:
        console.print(
            f"[red]Erro ao escrever no arquivo de contexto: {e}[/red]", file=sys.stderr
        )

def reset_context():
    """Reseta o contexto para 'home' (Estado Neutro), respeitando o isolamento de sessão."""
    write_context("home")


def load_env():
    """Carrega variáveis de ambiente do arquivo .env (se existir)."""
    env_path = get_project_root() / ".env"
    if env_path.exists():
        # Tenta usar python-dotenv para parsing robusto (suporte a aspas, multiline, etc)
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            return
        except ImportError:
            pass

        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    # Remove aspas e espaços
                    v = v.strip().strip("'").strip('"')
                    if k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


def setup_logging():
    """Configura logging global para arquivo."""
    root = get_project_root()
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)

    log_format = (
        "%(asctime)s [%(levelname)s] [%(project_context)s] %(module)s: %(message)s"
    )

    logging.basicConfig(
        filename=log_dir / "system.log",
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        encoding="utf-8",
    )

    # Adiciona o filtro a todos os loggers para injetar o contexto
    for handler in logging.root.handlers:
        handler.addFilter(ContextFilter())


# Configura logging automaticamente ao importar o módulo
setup_logging()
load_env()


def log_info(message: str):
    logging.info(message)
    console.print(f"[blue]ℹ️  {message}[/blue]")


def log_success(message: str):
    logging.info(f"SUCCESS: {message}")
    console.print(f"[green]✅ {message}[/green]")


def log_warning(message: str):
    logging.warning(message)
    console.print(f"[yellow]⚠️  {message}[/yellow]")


def log_error(message: str):
    logging.error(message)
    console.print(f"[red]❌ {message}[/red]")


def require_confirmation(prompt: str) -> bool:
    """Pede confirmação ao usuário."""
    response = console.input(
        f"[yellow]{prompt} [/yellow] Digite 'yes' para confirmar: "
    )
    return response.lower() == "yes"


@functools.lru_cache(maxsize=1)
def get_tool_versions():
    """Retorna as versões detectadas do AWS CLI e Terraform."""
    aws_v, tf_v = "N/A", "N/A"
    try:
        # Ex: aws-cli/2.15.30 ...
        out = subprocess.check_output(["aws", "--version"], text=True).split()[0]
        aws_v = out.replace("aws-cli/", "v")
    except:
        pass

    try:
        # Ex: Terraform v1.5.7 ...
        out = subprocess.check_output(
            ["terraform", "--version"], text=True
        ).splitlines()[0]
        tf_v = out.replace("Terraform ", "")
    except:
        pass
    return aws_v, tf_v


def normalize_project_name(name: str) -> str:
    """
    Normaliza o nome do projeto.
    Implementação Python otimizada (evita overhead de subprocesso da CLI Go).
    """
    s = name.lower()
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def validate_project_name(name: str) -> tuple[bool, str]:
    """
    Valida o nome do projeto.
    Implementação Python otimizada.
    """
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, "Nome inválido (apenas letras minúsculas, números e hífens)"
    return True, ""

@functools.lru_cache(maxsize=1)
def resolve_local_binary(binary_name: str) -> str:
    """
    Resolve o caminho absoluto de um binário local (ex: aponte) se existir no projeto.
    Caso contrário, retorna o nome original para busca no PATH.
    """
    if binary_name == "aponte":
        root = get_project_root()
        bin_path = root / "bin" / "aponte"
        if bin_path.exists():
            return str(bin_path)
    return binary_name
