#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Setup paths
project_root = Path(__file__).parents[2].resolve()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from core.lib import aws  # noqa: E402
from core.lib import utils as common  # noqa: E402

# Opcional: Boto3 para acesso direto a funcionalidades específicas
try:
    from boto3.dynamodb.conditions import Key
except ImportError:
    Key = None


def generate_snapshot():
    """Coleta métricas da AWS e salva em um JSON estático."""
    data = {
        "timestamp": datetime.now().isoformat(),
        "aws": {"status": "disconnected", "account": "unknown", "region": "unknown"},
        "project": {"name": "unknown"},
    }

    # 1. Project Context
    try:
        data["project"]["name"] = common.read_context()
    except Exception as e:
        data["project"]["error"] = str(e)

    # 2. AWS Connection & Identity
    try:
        session = aws.get_session()
        sts = session.client("sts")
        identity = sts.get_caller_identity()

        account = identity["Account"]
        region = session.region_name or os.getenv("AWS_REGION", "sa-east-1")

        data["aws"]["account"] = account
        data["aws"]["region"] = region
        data["aws"]["status"] = "connected"

        # 3. CloudWatch Alarms
        try:
            cw = session.client("cloudwatch")
            alarms = cw.describe_alarms(StateValue="ALARM")
            data["aws"]["alarms"] = {
                "count": len(alarms["MetricAlarms"]),
                "items": [a["AlarmName"] for a in alarms["MetricAlarms"][:5]],
            }
        except Exception as e:
            data["aws"]["alarms"] = {"error": str(e)}

        # 4. FinOps (Budgets)
        try:
            budgets = session.client("budgets")
            res = budgets.describe_budget(
                AccountId=account,
                BudgetName=os.getenv("APONTE_BUDGET_NAME", "a-ponte-monthly-budget"),
            )
            b = res["Budget"]

            limit = float(b["BudgetLimit"]["Amount"])
            actual = float(b["CalculatedSpend"]["ActualSpend"]["Amount"])
            percent = (actual / limit * 100) if limit > 0 else 0.0

            data["aws"]["finops"] = {
                "actual": actual,
                "limit": limit,
                "percent": percent,
            }
        except Exception as e:
            data["aws"]["finops"] = {"error": str(e)}

        # 5. AI History (DynamoDB)
        try:
            if not Key:
                raise ImportError("boto3 is required for DynamoDB history access.")
            dynamodb = session.resource("dynamodb")
            table = dynamodb.Table("a-ponte-ai-history")

            # Usa o nome do projeto descoberto anteriormente
            p_name = data["project"]["name"]

            if p_name and p_name != "unknown":
                response = table.query(
                    KeyConditionExpression=Key("ProjectName").eq(p_name),
                    ScanIndexForward=False,
                    Limit=1,
                )
                if response.get("Items"):
                    item = response["Items"][0]
                    data["ai_history"] = {
                        "ErrorSnippet": item.get("ErrorSnippet", ""),
                        "Timestamp": item.get("Timestamp", ""),
                    }
            else:
                data["ai_history"] = {"error": "Project context is missing or unknown"}
        except Exception as e:
            data["ai_history"] = {"error": str(e)}

    except Exception as e:
        data["aws"]["error"] = str(e)

    # 6. Security (A-PONTE Custom Ingestor)
    # Substitui DefectDojo pelo relatório JSON nativo gerado pelo 'aponte security audit'
    project_name = data.get("project", {}).get("name", "unknown")
    security_report = (
        project_root / "logs" / "security_reports" / f"{project_name}.json"
    )

    if security_report.exists():
        try:
            # Validação temporal: ignora relatórios muito antigos para não poluir o snapshot
            if (datetime.now().timestamp() - security_report.stat().st_mtime) > (
                86400 * 7
            ):  # 7 dias
                raise FileNotFoundError("Relatório de segurança muito antigo.")

            with open(security_report, "r") as f:
                findings = json.load(f)

            # Contagem por severidade
            summary = {
                "CRITICAL": 0,
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0,
                "INFO": 0,
                "UNKNOWN": 0,
            }
            for finding in findings:
                sev = finding.get("severity", "UNKNOWN").upper()
                if sev in summary:
                    summary[sev] += 1
                else:
                    summary["UNKNOWN"] += 1

            data["security"] = {
                "status": "active",
                "source": "security_report.json",
                "timestamp": datetime.fromtimestamp(
                    security_report.stat().st_mtime
                ).isoformat(),
                "metrics": summary,
                "total_findings": len(findings),
            }
        except Exception as e:
            data["security"] = {"status": "error", "error": str(e)}
    else:
        data["security"] = {
            "status": "missing_report",
            "message": "Relatório centralizado não encontrado. Execute o pipeline de segurança.",
        }

    # 7. Persistência
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "observability_state.json", "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Snapshot gerado em: {log_dir / 'observability_state.json'}")


if __name__ == "__main__":
    generate_snapshot()
