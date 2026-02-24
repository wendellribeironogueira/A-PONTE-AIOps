import os
import sys
import pytest
import boto3
from moto import mock_aws

# Adiciona a raiz do projeto ao path para imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.services import mcp_aws_reader


@pytest.fixture
def aws_credentials():
    """Credenciais fictícias para o Moto (Segurança)."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_REGION"] = "sa-east-1"


@mock_aws
def test_list_cloudwatch_alarms(aws_credentials):
    # 1. Setup: Cria o estado inicial na AWS simulada (Moto)
    cw = boto3.client("cloudwatch", region_name="sa-east-1")
    cw.put_metric_alarm(
        AlarmName="HighCPU",
        MetricName="CPUUtilization",
        Namespace="AWS/EC2",
        Period=300,
        EvaluationPeriods=1,
        Threshold=80.0,
        ComparisonOperator="GreaterThanOrEqualToThreshold",
    )

    # Define o estado do alarme explicitamente (put_metric_alarm define a regra, set_alarm_state define o estado)
    cw.set_alarm_state(
        AlarmName="HighCPU", StateValue="ALARM", StateReason="Threshold Crossed"
    )

    # 2. Execução: Chama a função real do MCP
    # A função vai instanciar o boto3 internamente, que será interceptado pelo Moto
    result = mcp_aws_reader.aws_list_cloudwatch_alarms.fn(state="ALARM")

    # 3. Validação: Verifica se a lógica do MCP processou corretamente o retorno da AWS
    assert "error" not in result
    alarms = result.get("alarms", [])
    assert len(alarms) == 1
    assert alarms[0]["name"] == "HighCPU"
    assert alarms[0]["state"] == "ALARM"
    assert alarms[0]["reason"] == "Threshold Crossed"


if __name__ == "__main__":
    pytest.main([__file__])
