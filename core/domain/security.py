from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    UNKNOWN = "UNKNOWN"


class ToolType(str, Enum):
    TRIVY = "trivy"  # Container & Filesystem
    PROWLER = "prowler"  # AWS Cloud Posture
    CHECKOV = "checkov"  # Infrastructure as Code (Terraform)
    GITLEAKS = "gitleaks"  # Secret Detection
    BANDIT = "bandit"  # Python SAST
    TFSEC = "tfsec"  # Security Scanner for Terraform
    TFLINT = "tflint"  # Terraform Linter
    OTHER = "other"


class FindingStatus(str, Enum):
    OPEN = "OPEN"
    FIXED = "FIXED"
    SUPPRESSED = "SUPPRESSED"


class SecurityFinding(BaseModel):
    """
    Modelo unificado para achados de segurança (A-PONTE Standard).
    Normaliza outputs de ferramentas como Trivy, Prowler e Checkov.
    """

    # Identificação Única
    id: str = Field(
        ..., description="Hash único do achado (ex: md5(tool+check_id+resource))"
    )
    project_name: str = Field(..., description="Tenant ID (Partition Key)")

    # Origem
    tool: ToolType = Field(..., description="Ferramenta de origem padronizada")
    check_id: str = Field(
        ..., description="ID original da verificação (ex: AWS-IAM-01, CVE-2023-1234)"
    )

    # Classificação
    severity: Severity
    status: FindingStatus = FindingStatus.OPEN

    # Descritivo
    title: str
    description: str
    remediation: Optional[str] = Field(None, description="Passos para correção")

    # Localização do Problema
    resource_id: Optional[str] = Field(
        None, description="ARN, File Path ou Container ID"
    )
    region: Optional[str] = Field(None, description="Região AWS (se aplicável)")
    line: Optional[int] = Field(None, description="Linha do código (para SAST)")

    # Metadados
    references: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True
