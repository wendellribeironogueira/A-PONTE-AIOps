#!/usr/bin/env python3
"""
Project Structure Mapper
------------------------
Gera um arquivo PROJECT_STRUCTURE.md na raiz do projeto contendo
a árvore de diretórios e arquivos, ignorando pastas de sistema/cache.
"""

import os
import sys
from pathlib import Path

# Setup paths (Robustez para execução direta)
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common

IGNORE_DIRS = {
    ".git",
    ".terraform",
    ".terragrunt-cache",
    "__pycache__",
    ".aponte-versions",
    ".idea",
    ".vscode",
    "node_modules",
    "venv",
    ".infracost",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".aws-sam",
}

IGNORE_FILES = {
    ".DS_Store",
    "thumbs.db",
    ".terraform.lock.hcl",
    "poetry.lock",
    "package-lock.json",
}


def generate_tree(dir_path: Path, prefix: str = ""):
    contents = []
    try:
        # Lista diretório
        for item in dir_path.iterdir():
            if item.name in IGNORE_DIRS or item.name in IGNORE_FILES:
                continue
            contents.append(item)
    except PermissionError:
        return

    # Ordena: Diretórios primeiro, depois arquivos (alfabético)
    contents.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

    # Prepara ponteiros gráficos
    pointers = (
        [("├── ", "│   ")] * (len(contents) - 1) + [("└── ", "    ")]
        if contents
        else []
    )

    for pointer, path in zip(pointers, contents):
        yield f"{prefix}{pointer[0]}{path.name}{'/' if path.is_dir() else ''}"
        if path.is_dir():
            yield from generate_tree(path, prefix + pointer[1])


def main():
    root = common.get_project_root()
    output_file = root / "PROJECT_STRUCTURE.md"

    common.log_info(f"Mapeando estrutura do projeto: {root.name}...")

    tree_lines = list(generate_tree(root))

    content = f"# 📂 Estrutura do Projeto: {root.name}\n\n"
    content += "> **Gerado automaticamente via `ia_ops/map_structure.py`**\n"
    content += f"> **Total de Arquivos/Pastas listados:** {len(tree_lines)}\n\n"
    content += "```text\n.\n"
    content += "\n".join(tree_lines)
    content += "\n```\n"

    output_file.write_text(content, encoding="utf-8")
    common.log_success(f"Arquivo gerado com sucesso: {output_file}")


if __name__ == "__main__":
    main()
