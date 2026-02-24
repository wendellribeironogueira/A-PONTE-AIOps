# 🔌 Guia de Integração e Mapa de Variáveis

Este documento destina-se a **Analistas de Cloud, DevOps e Desenvolvedores** que precisam criar infraestrutura (Terraform) ou pipelines (GitHub Actions) compatíveis com a plataforma **A-PONTE**.

Aqui você encontrará o "contrato" de variáveis e segredos que a plataforma injeta no seu ambiente.

---

## 🗺️ Mapa de Variáveis

### 1. GitHub Actions (CI/CD)

Ao vincular um repositório a um projeto (`aponte repo add`), o A-PONTE injeta automaticamente os seguintes valores no GitHub:

| Nome                       | Tipo         | Descrição                                                                      | Uso Obrigatório?           |
| -------------------------- | ------------ | ------------------------------------------------------------------------------ | -------------------------- |
| `AWS_ROLE_TO_ASSUME`       | **Secret**   | ARN da Role IAM que o GitHub Actions deve assumir via OIDC.                    | ✅ Sim (para autenticação) |
| `PERMISSIONS_BOUNDARY_ARN` | **Variable** | ARN da Policy de Boundary que **DEVE** ser anexada a qualquer Role IAM criada. | ✅ Sim (para compliance)   |
| `AWS_SUPPORT_ROLE_ARN`     | **Secret**   | ARN da Role de Break-Glass (se existir).                                       | ❌ Não (uso interno)       |

#### Exemplo de Workflow (`.github/workflows/deploy.yml`)

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write # Obrigatório para OIDC
      contents: read
    steps:
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
          aws-region: sa-east-1
```

### 2. Terraform (Inputs)

Quando você executa comandos via CLI (`aponte`) ou via CI/CD configurado pelo A-PONTE, as seguintes variáveis de ambiente são mapeadas para variáveis do Terraform (`TF_VAR_...`):

| Variável de Ambiente  | Input Terraform (`var.*`) | Descrição                               | Valores Possíveis                         |
| --------------------- | ------------------------- | --------------------------------------- | ----------------------------------------- |
| `TF_VAR_project_name` | `project_name`            | Nome do projeto (ex: `ecommerce-prod`). | String (sanitizada)                       |
| `TF_VAR_environment`  | `environment`             | Ambiente de deploy.                     | `development`, `staging`, `production`    |
| `TF_VAR_aws_region`   | `aws_region`              | Região AWS alvo.                        | ex: `sa-east-1`                           |
| `TF_VAR_app_name`     | `app_name`                | Nome da aplicação (lógica de negócio).  | ex: `ecommerce`                           |
| `TF_VAR_resource_name`| `resource_name`           | Nome do componente principal da infra.  | `web-server`, `assets-bucket`, `main-db`  |

#### Exemplo de `variables.tf` (No seu projeto)

Para que seu código Terraform receba esses valores, declare as variáveis:

```hcl
variable "project_name" {
  type        = string
  description = "Injetado automaticamente pelo A-PONTE"
}

variable "environment" {
  type        = string
  description = "Injetado automaticamente (development, staging, production)"
}

variable "aws_region" {
  type        = string
  default     = "sa-east-1"
}

variable "app_name" {
  type        = string
  description = "Nome da aplicação (ex: ecommerce)"
}

variable "resource_name" {
  type        = string
  description = "Nome do componente principal (ex: web-server)"
}
```

---

## 🛡️ Compliance e Governança

### Regra de Ouro: Permissions Boundary

Para garantir a segurança da plataforma, **toda Role IAM** criada pelos seus projetos deve ter o `permissions_boundary` anexado. Se você esquecer, a criação da Role falhará (bloqueio via SCP/Boundary da Role de Deploy).

#### Como implementar no Terraform:

```hcl
# 1. Declare a variável (injetada pelo GitHub Actions ou CLI)
variable "permissions_boundary_arn" {
  type        = string
  description = "ARN do Boundary de Segurança (Injetado pelo A-PONTE)"
  default     = null # Opcional para rodar local sem A-PONTE, mas obrigatório no apply real
}

# 2. Use no recurso
resource "aws_iam_role" "my_app_role" {
  name = "my-app-role"

  # ... assume_role_policy ...

  # ✅ OBRIGATÓRIO
  permissions_boundary = var.permissions_boundary_arn
}
```

---

## 🏷️ Estratégia de Tags

O A-PONTE não impõe tags via variável global complexa, mas recomenda o seguinte padrão para rastreabilidade de custos:

```hcl
locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

resource "aws_s3_bucket" "example" {
  bucket = "${var.project_name}-example"
  tags   = local.common_tags
}
```
