#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Literal

from fastmcp import FastMCP
from botocore.exceptions import ClientError

from core.lib import aws
from core.lib.mcp_utils import handle_mcp_errors

# Inicializa o servidor FastMCP
mcp = FastMCP("aws_reader")


def _get_client(service_name: str):
    """Helper para obter cliente AWS via sessão, garantindo consistência com core.lib."""
    region = os.getenv("AWS_REGION", "sa-east-1")
    return aws.get_session(region).client(service_name)


@mcp.tool(name="aws_list_resources")
@handle_mcp_errors
def aws_list_resources(
    resource_type_filters: list[str] = None, query: Optional[str] = None, tags_per_page: Optional[int] = 50, pagination_token: Optional[str] = None, project_name: Optional[str] = None
) -> dict:
    """
    Lista recursos AWS (ARNs e Tags). Use para descobrir recursos existentes quando não souber o serviço específico.

    Args:
        resource_type_filters: Lista de tipos (ex: ['s3', 'ec2:instance'])

    Examples:
        resource_type_filters=['s3']
    """
    client = _get_client("resourcegroupstaggingapi")

    kwargs = {"ResourcesPerPage": tags_per_page or 50}

    # Smart Filter: Se project_name for fornecido, filtra por Tag Project
    if project_name:
        kwargs["TagFilters"] = [{"Key": "Project", "Values": [project_name]}]

    if resource_type_filters:
        kwargs["ResourceTypeFilters"] = resource_type_filters
    if pagination_token:
        kwargs["PaginationToken"] = pagination_token

    response = client.get_resources(**kwargs)

    resources = []
    for item in response["ResourceTagMappingList"]:
        resources.append(
            {
                "arn": item["ResourceARN"],
                "tags": {t["Key"]: t["Value"] for t in item.get("Tags", [])},
            }
        )

    next_token = response.get("PaginationToken", "")
    truncated = bool(next_token)

    if query:
        # Filtro em memória para robustez
        resources = [r for r in resources if query.lower() in r['arn'].lower() or any(query.lower() in str(v).lower() for v in r['tags'].values())]

    return {
        "resources": resources,
        "count": len(resources),
        "next_token": next_token,
        "truncated": truncated,
        "note": "Use 'pagination_token' with the next_token value to fetch more." if truncated else ""
    }


@mcp.tool(name="aws_list_cloudwatch_alarms")
@handle_mcp_errors
def aws_list_cloudwatch_alarms(state: Literal["ALARM", "OK", "INSUFFICIENT_DATA"] = "ALARM", name_prefix: Optional[str] = None, query: Optional[str] = None, limit: Optional[int] = 50, next_token: Optional[str] = None, project_name: Optional[str] = None) -> dict:
    """
    Lista alarmes do CloudWatch que estão *atualmente* em um estado específico. Use para ver o status imediato do sistema e incidentes ativos.

    Args:
        state: Estado do alarme (ALARM, OK, INSUFFICIENT_DATA)

    Examples:
        state='ALARM'
    """
    client = _get_client("cloudwatch")

    # Robustez: Se a IA enviar string vazia, assume o padrão ALARM
    if not state or not state.strip():
        state = "ALARM"

    if not name_prefix and not query and project_name:
        name_prefix = project_name

    kwargs = {"StateValue": state, "MaxRecords": limit or 50}
    if name_prefix:
        kwargs["AlarmNamePrefix"] = name_prefix
    elif query:
        kwargs["AlarmNamePrefix"] = query
    if next_token:
        kwargs["NextToken"] = next_token

    response = client.describe_alarms(**kwargs)
    alarms = []
    for alarm in response["MetricAlarms"]:
        alarms.append(
            {
                "name": alarm["AlarmName"],
                "state": alarm["StateValue"],
                "reason": alarm["StateReason"],
                "metric": alarm["MetricName"],
            }
        )
    return {
        "alarms": alarms,
        "count": len(alarms),
        "next_token": response.get("NextToken")
    }


@mcp.tool(name="aws_list_alarm_history")
@handle_mcp_errors
def aws_list_alarm_history(
    alarm_name: Optional[str] = None, query: Optional[str] = None, hours_ago: int = 24, start_time: Optional[str] = None, end_time: Optional[str] = None, limit: Optional[int] = 50, next_token: Optional[str] = None, project_name: Optional[str] = None
) -> dict:
    """
    LISTAR histórico de alarmes. Use quando o usuário pedir para 'listar alarmes', 'ver histórico' ou investigar incidentes recentes.

    Args:
        alarm_name: Nome exato do alarme (opcional)

    Examples:
        hours_ago=24
    """
    client = _get_client("cloudwatch")

    if start_time:
        try:
            start_date = datetime.strptime(start_time, "%d/%m/%Y")
        except ValueError:
            start_date = datetime.now() - timedelta(hours=hours_ago)
    else:
        start_date = datetime.now() - timedelta(hours=hours_ago)

    kwargs = {
        "HistoryItemType": "StateUpdate",
        "StartDate": start_date,
        "MaxRecords": limit or 50,
    }

    if end_time:
        try:
            kwargs["EndDate"] = datetime.strptime(end_time, "%d/%m/%Y") + timedelta(days=1) - timedelta(seconds=1)
        except ValueError:
            pass

    if alarm_name:
        kwargs["AlarmName"] = alarm_name
    if next_token:
        kwargs["NextToken"] = next_token

    response = client.describe_alarm_history(**kwargs)

    history = []
    for item in response.get("AlarmHistoryItems", []):
        history.append({
            "alarm_name": item.get("AlarmName"),
            "timestamp": item.get("Timestamp").isoformat(),
            "summary": item.get("HistorySummary"),
            "data": json.loads(item.get("HistoryData", "{}"))
        })

    if query:
        history = [h for h in history if query.lower() in h['summary'].lower() or query.lower() in json.dumps(h['data']).lower()]
    elif project_name:
        history = [h for h in history if project_name.lower() in (h.get('alarm_name') or "").lower()]

    return {"history": history, "count": len(history), "next_token": response.get("NextToken")}

@mcp.tool(name="aws_get_cost_forecast")
@handle_mcp_errors
def aws_get_cost_forecast(project_name: Optional[str] = None) -> dict:
    """
    Obtém previsão de custos. Use para responder perguntas sobre FinOps, orçamento ou gastos mensais.

    Examples:
        project_name='ecommerce-prod'
    """
    client = _get_client("ce")

    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=30)).replace(day=1).strftime("%Y-%m-%d")

    try:
        kwargs = {
            "TimePeriod": {"Start": start, "End": end},
            "Metric": "UNBLENDED_COST",
            "Granularity": "MONTHLY",
        }
        if project_name:
            kwargs["Filter"] = {"Tags": {"Key": "Project", "Values": [project_name]}}

        response = client.get_cost_forecast(**kwargs)
        return {
            "forecast": response["Total"]["Amount"],
            "unit": response["Total"]["Unit"],
        }
    except ClientError as e:
        if e.response['Error']['Code'] == 'DataUnavailableException':
            return {"error": "Cost Explorer data is not available yet (New account or processing)."}
        return {"error": f"AWS API Error: {e}"}


@mcp.tool(name="aws_check_cloudtrail")
@handle_mcp_errors
def aws_check_cloudtrail(query: Optional[str] = None, project_name: Optional[str] = None) -> dict:
    """
    Verifica status do CloudTrail. Use para auditoria de segurança e garantir que os logs estão ativos.

    Examples:
        query='management-events'
    """
    client = _get_client("cloudtrail")
    response = client.describe_trails()
    trails = response.get("trailList", [])
    result = []
    for t in trails:
        status = client.get_trail_status(Name=t["TrailARN"])
        result.append(
            {
                "name": t["Name"],
                "is_logging": status["IsLogging"],
                "multi_region": t.get("IsMultiRegionTrail", False),
            }
        )

    if query:
        result = [t for t in result if query.lower() in t['name'].lower()]
    elif project_name:
        result = [t for t in result if project_name.lower() in t['name'].lower()]

    return {
        "trails": result,
        "count": len(result),
        "note": "Free Tier: 1 trilha de gerenciamento é gratuita.",
    }


@mcp.tool(name="aws_list_log_groups")
@handle_mcp_errors
def aws_list_log_groups(name_prefix: str = "", query: Optional[str] = None, limit: Optional[int] = 20, next_token: Optional[str] = None, project_name: Optional[str] = None) -> dict:
    """
    Lista grupos de logs. Use para encontrar onde os logs de uma aplicação ou recurso estão armazenados.

    Args:
        name_prefix: Prefixo para filtrar grupos (ex: /aws/lambda)

    Examples:
        name_prefix='/aws/lambda/'
    """
    client = _get_client("logs")

    params = {"limit": limit or 20}
    if name_prefix:
        params["logGroupNamePrefix"] = name_prefix
    elif query:
        params["logGroupNamePrefix"] = query
    elif project_name:
        params["logGroupNamePrefix"] = project_name
    if next_token:
        params["nextToken"] = next_token

    response = client.describe_log_groups(**params)
    groups = [g["logGroupName"] for g in response.get("logGroups", [])]

    return {
        "log_groups": groups,
        "count": len(groups),
        "next_token": response.get("nextToken"),
        "note": "Use 'next_token' to fetch more groups." if response.get("nextToken") else ""
    }


@mcp.tool(name="aws_filter_log_events")
@handle_mcp_errors
def aws_filter_log_events(
    log_group_name: str, filter_pattern: str = "", query: Optional[str] = None, hours_ago: int = 1, limit: Optional[int] = 20, next_token: Optional[str] = None, project_name: Optional[str] = None
) -> dict:
    """
    LER logs recentes do CloudWatch. Use para 'listar logs', 'ver erros' ou investigar o comportamento de uma aplicação.

    Args:
        log_group_name: Nome do grupo de log
        filter_pattern: Sintaxe de filtro CloudWatch

    Examples:
        filter_pattern='ERROR'
    """
    client = _get_client("logs")

    start_time = int((datetime.now() - timedelta(hours=hours_ago)).timestamp() * 1000)

    params = {
        "logGroupName": log_group_name,
        "startTime": start_time,
        "limit": limit or 20,
    }
    if filter_pattern:
        params["filterPattern"] = filter_pattern
    elif query:
        params["filterPattern"] = query
    if next_token:
        params["nextToken"] = next_token

    response = client.filter_log_events(**params)
    events = []
    for e in response.get("events", []):
        # Formata timestamp para legibilidade
        ts = datetime.fromtimestamp(e["timestamp"] / 1000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        events.append(f"[{ts}] {e['message']}")

    return {
        "events": events,
        "count": len(events),
        "next_token": response.get("nextToken")
    }

@mcp.tool(name="aws_lookup_events")
@handle_mcp_errors
def aws_lookup_events(
    query: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: Optional[int] = 50,
    next_token: Optional[str] = None,
    project_name: Optional[str] = None
) -> dict:
    """
    Consulta histórico de eventos de API (CloudTrail). Use para auditoria e segurança.

    Args:
        start_time: Data inicial (DD/MM/YYYY)
        end_time: Data final (DD/MM/YYYY)
    """
    client = _get_client("cloudtrail")

    kwargs = {"MaxResults": limit or 50}

    if start_time:
        try:
            kwargs["StartTime"] = datetime.strptime(start_time, "%d/%m/%Y")
        except ValueError:
            pass

    if end_time:
        try:
            kwargs["EndTime"] = datetime.strptime(end_time, "%d/%m/%Y") + timedelta(days=1) - timedelta(seconds=1)
        except ValueError:
            pass

    if next_token:
        kwargs["NextToken"] = next_token

    response = client.lookup_events(**kwargs)

    events = []
    for e in response.get("Events", []):
        events.append({
            "time": e["EventTime"].isoformat(),
            "name": e["EventName"],
            "user": e.get("Username"),
            "source": e.get("EventSource"),
            "resources": [r["ResourceName"] for r in e.get("Resources", [])]
        })

    return {"events": events, "count": len(events), "next_token": response.get("NextToken")}

@mcp.tool(name="aws_simulate_principal_policy")
@handle_mcp_errors
def aws_simulate_principal_policy(
    policy_source_arn: str, action_names: list[str], resource_arns: list[str] = None, project_name: Optional[str] = None
) -> dict:
    """
    Simula permissões IAM. Use para verificar se um usuário ou role tem acesso a um recurso específico (Troubleshooting de Acesso).

    Args:
        action_names: Lista de ações (ex: ['s3:ListBucket'])

    Examples:
        action_names=['s3:GetObject', 's3:PutObject']
    """
    client = _get_client("iam")

    try:
        kwargs = {
            "PolicySourceArn": policy_source_arn,
            "ActionNames": action_names,
        }
        if resource_arns:
            kwargs["ResourceArns"] = resource_arns

        response = client.simulate_principal_policy(**kwargs)

        results = []
        for res in response.get("EvaluationResults", []):
            results.append({
                "action": res.get("EvalActionName"),
                "decision": res.get("EvalDecision"),
                "resource": res.get("EvalResourceName"),
            })

        if project_name:
            results = [r for r in results if project_name.lower() in (r["resource"] or "").lower()]

        return {"results": results}
    except ClientError as e:
        return {"error": f"AWS API Error: {e}"}


@mcp.tool(name="aws_list_buckets")
@handle_mcp_errors
def aws_list_buckets(query: Optional[str] = None, project_name: Optional[str] = None) -> dict:
    """
    Lista buckets S3 da conta. Use para ver o armazenamento disponível, localizar buckets de logs ou verificar buckets de um projeto específico.

    Args:
        query: Filtro de nome parcial

    Examples:
        query='logs'
    """
    client = _get_client("s3")
    response = client.list_buckets()
    all_buckets = []
    for b in response.get("Buckets", []):
        all_buckets.append({
            "name": b["Name"],
            "creation_date": b["CreationDate"].isoformat() if b.get("CreationDate") else None
        })

    buckets = all_buckets
    if query:
        buckets = [b for b in buckets if query.lower() in b["name"].lower()]
    elif project_name:
        buckets = [b for b in buckets if project_name.lower() in b["name"].lower()]

    return {
        "buckets": buckets,
        "count": len(buckets),
        "total_in_account": len(all_buckets),
        "debug_filter": f"query='{query}', project='{project_name}'"
    }


@mcp.tool(name="aws_list_ec2_instances")
@handle_mcp_errors
def aws_list_ec2_instances(state: Optional[Literal["pending", "running", "shutting-down", "terminated", "stopping", "stopped"]] = None, query: Optional[str] = None, limit: Optional[int] = 20, next_token: Optional[str] = None, project_name: Optional[str] = None, status: Optional[str] = None) -> dict:
    """
    Lista instâncias EC2. Use para ver servidores rodando, seus IPs e status (running/stopped).

    Args:
        state: Filtro de estado (running, stopped)

    Examples:
        state='running'
    """
    client = _get_client("ec2")
    # Robustez: Trata alucinações comuns de parâmetros
    if not state and status:
        state = status

    filters = []
    if state:
        filters.append({"Name": "instance-state-name", "Values": [state]})

    if query:
        filters.append({"Name": "tag:Name", "Values": [f"*{query}*"]})
    elif project_name:
        # Se não houver query específica, filtra por tag Project ou Name contendo o projeto
        filters.append({"Name": "tag:Project", "Values": [project_name]})

    kwargs = {"Filters": filters, "MaxResults": limit or 20}
    if next_token:
        kwargs["NextToken"] = next_token

    response = client.describe_instances(**kwargs)
    instances = []
    for r in response.get("Reservations", []):
        for i in r.get("Instances", []):
            name = "N/A"
            for t in i.get("Tags", []):
                if t["Key"] == "Name":
                    name = t["Value"]
                    break
            instances.append({
                "id": i["InstanceId"],
                "name": name,
                "type": i["InstanceType"],
                "state": i["State"]["Name"],
                "public_ip": i.get("PublicIpAddress", "N/A"),
                "private_ip": i.get("PrivateIpAddress", "N/A")
            })
    return {
        "instances": instances,
        "count": len(instances),
        "next_token": response.get("NextToken")
    }

# ==============================================================================
# MCP RESOURCES (Leitura de Estado como Arquivo)
# ==============================================================================

@mcp.resource("aws://identity")
def get_aws_identity() -> str:
    """Retorna a identidade atual da conta AWS (Account, ARN, UserId)."""
    try:
        session = aws.get_session()
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        return json.dumps(identity, indent=2, default=str)
    except Exception as e:
        return f"Error fetching identity: {str(e)}"

@mcp.resource("aws://region")
def get_aws_region() -> str:
    """Retorna a região AWS ativa na sessão."""
    return os.getenv("AWS_REGION", "sa-east-1")

@mcp.resource("aws://cloudwatch/alarms")
def get_alarms_resource() -> str:
    """Recurso que contém a lista de alarmes ativos (ALARM) em texto plano."""
    try:
        client = _get_client("cloudwatch")
        response = client.describe_alarms(StateValue="ALARM")
        alarms = [
            f"- {a['AlarmName']}: {a['StateReason']}"
            for a in response.get("MetricAlarms", [])
        ]
        return "\n".join(alarms) if alarms else "✅ No active alarms."
    except Exception as e:
        return f"Error reading alarms: {str(e)}"

# ==============================================================================
# MCP PROMPTS (Templates de Raciocínio)
# ==============================================================================

@mcp.prompt()
def sre_incident_triage(service_name: str = "unknown", error_snippet: str = "") -> str:
    """Template de Triage SRE: Guia a IA para diagnosticar incidentes AWS."""
    return f"""
    Você está atuando como um Engenheiro de Confiabilidade de Site (SRE) Sênior no A-PONTE.

    🚨 INCIDENTE REPORTADO:
    - Serviço Suspeito: {service_name}
    - Sintoma/Erro: {error_snippet}

    PLAYBOOK DE INVESTIGAÇÃO (Siga estes passos):
    1. **Identidade & Contexto**: Confirme onde estamos lendo o recurso 'aws://identity' e 'aws://region'.
    2. **Saúde Imediata**: Leia o recurso 'aws://cloudwatch/alarms' para ver se há falhas conhecidas.
    3. **Logs Recentes**: Use a ferramenta 'aws_filter_log_events' no Log Group do serviço '{service_name}'.
    4. **Auditoria**: Se houver suspeita de mudança manual, use 'aws_check_cloudtrail'.

    Gere um relatório de causa raiz com base nas evidências coletadas.
    """

if __name__ == "__main__":
    mcp.run()
