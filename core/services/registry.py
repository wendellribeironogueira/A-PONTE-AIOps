import os
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError
from core.lib import aws

# Nome da tabela definido na CLI Go (cli/cmd/setup.go)
TABLE_NAME = os.getenv("APONTE_REGISTRY_TABLE", "a-ponte-registry")


def _get_table():
    """Retorna o recurso Table do DynamoDB configurado."""
    dynamodb = aws.get_resource("dynamodb")
    return dynamodb.Table(TABLE_NAME)


def get_project(project_name: str) -> Optional[Dict[str, Any]]:
    """
    Busca metadados de um projeto no Registry (DynamoDB).
    Retorna None se o projeto não existir.
    """
    try:
        table = _get_table()
        response = table.get_item(Key={"ProjectName": project_name})
        return response.get("Item")
    except ClientError as e:
        # Se a tabela não existir (ambiente não bootstrapped), assume vazio
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return None
        # Outros erros (permissão, throttling) devem ser logados/tratados
        print(f"⚠️  Erro ao acessar Registry DynamoDB: {e}")
        return None


def check_exists(project_name: str) -> bool:
    """Verifica se um projeto já está registrado na plataforma."""
    return get_project(project_name) is not None
