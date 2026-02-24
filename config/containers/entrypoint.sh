#!/bin/sh
set -e

# This script acts as a robust entrypoint for the mcp-terraform container.
# It handles path resolution and provides diagnostics on failure.

SCRIPT_PATH="mcp_terraform.py" # Alterado: Garante execução do script principal (ADR-028)
SCRIPT_REL="core/services/${SCRIPT_PATH}"

# 1. Try to find the script in the standard locations
if [ -f "/app/${SCRIPT_REL}" ]; then
    export PYTHONPATH=$PYTHONPATH:/app
    echo "Diagnostic: /app/${SCRIPT_REL} found" >&2

    # Pre-flight check: Garante que dependências críticas estão carregáveis
    python3 -c "import fastmcp; import boto3; import requests" 2>/dev/null || {
        echo "❌ Critical: Dependencies (fastmcp/boto3) missing or broken in container." >&2
        exit 1
    }

    # Executa com -u (unbuffered) para garantir que logs fluam imediatamente
    exec python3 -u "/app/${SCRIPT_REL}" "$@"
elif [ -f "/src/${SCRIPT_REL}" ]; then
   export PYTHONPATH=$PYTHONPATH:/src
    exec python3 "/src/${SCRIPT_REL}" "$@"
elif [ -f "/app/${SCRIPT_PATH}" ]; then
    export PYTHONPATH=$PYTHONPATH:/app
    exec python3 "/app/${SCRIPT_PATH}" "$@"
else
   # 2. If not found, provide detailed diagnostics
    echo "❌ Erro Crítico: Script ${SCRIPT_REL} (ou ${SCRIPT_PATH}) não encontrado no container." >&2
    echo "Diagnóstico de Volume:" >&2
    echo "User: $(id -u):$(id -g)" >&2

    if [ -d "/app" ]; then
        ls -ld /app >&2
        if [ -z "$(ls -A /app)" ]; then
            echo "⚠️  Diretório /app está vazio. O volume não foi montado corretamente." >&2
            echo "👉 SOLUÇÃO: O volume do container foi perdido ou não montado." >&2
            echo "   Execute: docker compose -f config/containers/docker-compose.yml up -d --force-recreate mcp-terraform" >&2
        else
            echo "Conteúdo de /app:" >&2
            ls -A /app | head -n 5 >&2
            echo "Busca por ${SCRIPT_PATH}:" >&2
            find /app -name "${SCRIPT_PATH}" 2>/dev/null | head -n 3 >&2
        fi
    else
        echo "⚠️ Diretório /app não existe." >&2
    fi

    exit 1
fi