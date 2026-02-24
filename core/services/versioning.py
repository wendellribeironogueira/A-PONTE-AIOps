#!/usr/bin/env python3
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import boto3

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import aws
from core.lib import utils as common

ROOT_DIR = common.get_project_root()
VERSIONS_DIR = ROOT_DIR / ".aponte-versions"
PROJECTS_STORE = VERSIONS_DIR / "projects"
STATES_STORE = VERSIONS_DIR / "states"
FILES_STORE = VERSIONS_DIR / "files"


def init_versioning():
    """Inicializa a estrutura de diretórios de versionamento."""
    if not VERSIONS_DIR.exists():
        common.log_info("Inicializando sistema de versionamento...")
        PROJECTS_STORE.mkdir(parents=True, exist_ok=True)
        STATES_STORE.mkdir(parents=True, exist_ok=True)
        FILES_STORE.mkdir(parents=True, exist_ok=True)

        index_file = VERSIONS_DIR / "index.json"
        if not index_file.exists():
            index_data = {
                "version": "1.0",
                "created": datetime.now().isoformat(),
                "projects": {},
            }
            index_file.write_text(json.dumps(index_data, indent=2))


def generate_version_id() -> str:
    return f"v{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"


def version_project_config(project: str, reason: str = "Manual backup"):
    """Cria snapshot dos arquivos de configuração locais."""
    init_versioning()
    version_id = generate_version_id()
    version_dir = PROJECTS_STORE / project / version_id
    version_dir.mkdir(parents=True, exist_ok=True)

    common.log_info(f"📝 Criando versão de projeto: {version_id}")

    # Arquivos a copiar
    projects_dir = ROOT_DIR / "projects"
    files_to_copy = [
        f"{project}.repos",
        f"{project}.auto.tfvars",
        f"{project}.project.yml",
    ]

    copied_files = []
    for fname in files_to_copy:
        src = projects_dir / fname
        if src.exists():
            shutil.copy2(src, version_dir / fname)
            copied_files.append(fname)

    # Obtém versão do Terraform usada neste backup
    _, tf_version = common.get_tool_versions()

    # Metadata
    metadata = {
        "project": project,
        "version_id": version_id,
        "timestamp": datetime.now().isoformat(),
        "user": aws.get_current_user(),
        "terraform_version": tf_version,
        "reason": reason,
        "files": copied_files,
    }

    (version_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    common.log_success(f"Versão de config criada: {version_id}")
    return version_dir


def version_terraform_state(project: str, region: str, reason: str = "Manual backup"):
    """Faz download do tfstate do S3 para backup local."""
    init_versioning()
    version_id = generate_version_id()
    version_dir = STATES_STORE / project / version_id
    version_dir.mkdir(parents=True, exist_ok=True)

    common.log_info(f"💾 Salvando versão de state: {version_id}")

    bucket_name = f"{project}-tfstate-bucket"
    if project != "a-ponte":
        # Lógica para projetos tenant (bucket centralizado)
        account_id = aws.get_account_id()
        bucket_name = f"a-ponte-central-tfstate-{account_id}"
        key = f"{project}/terraform.tfstate"
    else:
        # Lógica legado/core
        key = "terraform.tfstate"

    s3 = aws.get_session(region).client("s3")

    try:
        dest_file = version_dir / "terraform.tfstate"
        s3.download_file(Bucket=bucket_name, Key=key, Filename=str(dest_file))

        file_size = dest_file.stat().st_size

        metadata = {
            "project": project,
            "version_id": version_id,
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "s3_bucket": bucket_name,
            "s3_key": key,
            "state_size": file_size,
        }
        (version_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        common.log_success(f"State versionado: {version_id} ({file_size} bytes)")

    except Exception as e:
        common.log_warning(
            f"Não foi possível baixar o state (pode não existir ainda): {e}"
        )


def version_generic_file(file_path: Path, project: str, reason: str = "AI Auto-Fix"):
    """Cria versão de um arquivo genérico (ex: .tf modificado pela IA)."""
    init_versioning()
    version_id = generate_version_id()

    # Normaliza o path para evitar problemas
    safe_filename = file_path.name

    version_dir = FILES_STORE / project / safe_filename / version_id
    version_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(file_path, version_dir / safe_filename)

    metadata = {
        "project": project,
        "original_path": str(file_path.resolve()),
        "version_id": version_id,
        "timestamp": datetime.now().isoformat(),
        "user": aws.get_current_user(),
        "reason": reason,
    }

    (version_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    return version_id


def list_versions(project: str, type_store: str = "projects"):
    """Lista versões disponíveis."""
    store = PROJECTS_STORE if type_store == "projects" else STATES_STORE
    target_dir = store / project

    if not target_dir.exists():
        common.log_warning(f"Nenhuma versão encontrada para {project} em {type_store}")
        return

    common.console.print(f"\n[bold]Versões de {type_store} para {project}:[/bold]")

    # Lista diretórios e ordena
    versions = sorted([d for d in target_dir.iterdir() if d.is_dir()], reverse=True)

    for v_dir in versions[:10]:  # Top 10
        meta_file = v_dir / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            ts = meta.get("timestamp", "")
            reason = meta.get("reason", "")
            common.console.print(f"  📦 {v_dir.name} | {ts} | {reason}")
        else:
            common.console.print(f"  📦 {v_dir.name} (Sem metadados)")


def rollback_project_config(project: str, version_id: str):
    """Restaura arquivos de configuração."""
    src_dir = PROJECTS_STORE / project / version_id
    if not src_dir.exists():
        common.log_error(f"Versão {version_id} não encontrada.")
        return

    common.log_warning(f"⚠️  Rollback de projeto: {project} -> {version_id}")
    if not common.require_confirmation(
        "Tem certeza? Configs atuais serão substituídas"
    ):
        return

    # Backup antes do rollback
    version_project_config(
        project, f"Pre-rollback backup (antes de restaurar {version_id})"
    )

    projects_dir = ROOT_DIR / "projects"
    for fname in ["repos", "auto.tfvars", "project.yml"]:
        full_name = f"{project}.{fname}"
        src_file = src_dir / full_name
        if src_file.exists():
            shutil.copy2(src_file, projects_dir / full_name)
            common.log_success(f"Restaurado: {full_name}")


def rollback_generic_file(project: str, file_name: str, version_id: str):
    """Restaura um arquivo versionado (ex: .tf modificado pela IA)."""
    version_dir = FILES_STORE / project / file_name / version_id
    if not version_dir.exists():
        common.log_error(f"Versão {version_id} do arquivo {file_name} não encontrada.")
        return

    metadata_file = version_dir / "metadata.json"
    if not metadata_file.exists():
        common.log_error("Metadados corrompidos.")
        return

    try:
        metadata = json.loads(metadata_file.read_text())
        original_path = Path(metadata["original_path"])

        common.log_warning(f"⚠️  Restaurando {file_name} para versão {version_id}...")
        if not common.require_confirmation(
            "O arquivo atual será sobrescrito. Continuar?"
        ):
            return

        # Cria backup de segurança do estado atual antes de sobrescrever (Safety First)
        if original_path.exists():
            version_generic_file(
                original_path,
                project,
                reason=f"Auto-backup before rollback to {version_id}",
            )

        src_file = version_dir / file_name
        if src_file.exists():
            shutil.copy2(src_file, original_path)
            common.log_success(f"Arquivo restaurado com sucesso: {original_path}")
        else:
            common.log_error("Arquivo de backup não encontrado no diretório de versão.")

    except Exception as e:
        common.log_error(f"Erro ao restaurar arquivo: {e}")


def main():
    if len(sys.argv) < 3:
        print("Uso: versioning.py <action> <project> [args...]")
        print(
            "Actions: backup-config, backup-state, list, rollback-config, rollback-file"
        )
        return

    action = sys.argv[1]
    project = sys.argv[2]

    if action == "backup-config":
        version_project_config(project)
    elif action == "backup-state":
        region = sys.argv[3] if len(sys.argv) > 3 else "sa-east-1"
        version_terraform_state(project, region)
    elif action == "list":
        list_versions(project, "projects")
        list_versions(project, "states")
    elif action == "rollback-config":
        version_id = sys.argv[3]
        rollback_project_config(project, version_id)
    elif action == "rollback-file":
        if len(sys.argv) < 5:
            print("Uso: versioning.py rollback-file <project> <filename> <version_id>")
            return
        file_name = sys.argv[3]
        version_id = sys.argv[4]
        rollback_generic_file(project, file_name, version_id)


if __name__ == "__main__":
    main()
