#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Setup paths para importar o core
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import utils as common


def get_principal_arn(sts_arn):
    """Converte ARN de AssumedRole para ARN de Role real para simulação."""
    if ":assumed-role/" in sts_arn:
        # arn:aws:sts::ACCOUNT:assumed-role/ROLE_NAME/SESSION
        parts = sts_arn.split("/")
        role_name = parts[1]
        account_id = sts_arn.split(":")[4]
        return f"arn:aws:iam::{account_id}:role/{role_name}", role_name
    return sts_arn, sts_arn.split("/")[-1]


def check_bootstrap_permissions():
    """
    Verifica programaticamente se a identidade atual tem permissões para o bootstrap.
    Retorna um dicionário com o diagnóstico para ser usado por outras ferramentas (Doctor).
    """
    region = os.getenv("AWS_REGION") or os.getenv("TF_VAR_aws_region") or "sa-east-1"
    try:
        sts = boto3.client("sts", region_name=region)
        identity = sts.get_caller_identity()
        current_arn = identity["Arn"]
        account_id = identity["Account"]
    except Exception as e:
        return {"error": f"Falha ao conectar na AWS: {e}"}

    iam = boto3.client("iam", region_name=region)
    principal_arn, entity_name = get_principal_arn(current_arn)

    # 1. Check Boundary
    boundary_arn = None
    try:
        if ":user/" in principal_arn:
            info = iam.get_user(UserName=entity_name)
            boundary_arn = (
                info["User"]
                .get("PermissionsBoundary", {})
                .get("PermissionsBoundaryArn")
            )
        elif ":role/" in principal_arn:
            info = iam.get_role(RoleName=entity_name)
            boundary_arn = (
                info["Role"]
                .get("PermissionsBoundary", {})
                .get("PermissionsBoundaryArn")
            )
    except ClientError as e:
        pass  # Best effort, pode falhar se não tiver permissão de leitura sobre si mesmo

    # 2. Simulate
    # Permite override via env var para testes ou setups customizados
    bucket_name = os.getenv(
        "APONTE_STATE_BUCKET", f"a-ponte-central-tfstate-{account_id}"
    )
    bucket_arn = f"arn:aws:s3:::{bucket_name}"
    table_arn = f"arn:aws:dynamodb:*:*:table/{os.getenv('APONTE_LOCK_TABLE_PREFIX', 'a-ponte-lock-')}*"

    actions = [
        "s3:CreateBucket",
        "s3:ListBucket",
        "s3:PutBucketVersioning",
        "s3:PutBucketEncryption",
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:PutItem",
    ]

    denied = []
    # Simula individualmente para evitar erro de "different authorization information"
    for action in actions:
        try:
            target_resource = bucket_arn if action.startswith("s3:") else table_arn
            results = iam.simulate_principal_policy(
                PolicySourceArn=principal_arn,
                ActionNames=[action],
                ResourceArns=[target_resource],
            )
            for res in results["EvaluationResults"]:
                if res["EvalDecision"] != "allowed":
                    denied.append(res["EvalActionName"])
        except ClientError as e:
            return {"error": f"Não foi possível simular a ação {action}: {e}"}

    return {"principal": principal_arn, "boundary": boundary_arn, "denied": denied}


def inspect():
    """CLI Wrapper para uso manual."""
    common.console.rule(
        "[bold magenta]🕵️  Iniciando Inspeção de Identidade e Permissões (IAM)[/]"
    )

    result = check_bootstrap_permissions()

    if "error" in result:
        common.log_error(result["error"])
        sys.exit(1)

    common.console.print(f"👤 Identidade: [bold cyan]{result['principal']}[/]")

    if result["boundary"]:
        common.console.print(
            f"[yellow]🚧 [ALERTA] Permissions Boundary Ativo: {result['boundary']}[/]"
        )
    else:
        common.console.print("[green]✅ Nenhum Permissions Boundary detectado.[/]")

    common.console.print("\n[bold]🧪 Resultado da Simulação:[/]")
    if result["denied"]:
        common.console.print(f"[red]❌ {len(result['denied'])} permissões negadas:[/]")
        for action in result["denied"]:
            common.console.print(f"   - {action}")
        common.console.print(
            "\n[bold red]❌ DIAGNÓSTICO: Política IAM impedindo bootstrap.[/]"
        )
    else:
        common.log_success(
            "Todas as permissões de bootstrap foram aprovadas na simulação."
        )


if __name__ == "__main__":
    inspect()
