# 🛠️ Plano de Remediação Técnica - A-PONTE

Este documento especifica as correções técnicas mandatórias para mitigar os riscos de segurança e bloqueios operacionais identificados na análise de arquitetura.

## 1. Segurança: Hardening de IAM (Prioridade Crítica)

**Vulnerabilidade:** A implementação atual permite a criação de Roles sem o _Permissions Boundary_ anexado, possibilitando a criação de usuários administradores (Escalação de Privilégio).

**Correção:** Adicionar condição `iam:PermissionsBoundary` na política da Role de CI/CD.

```hcl
# terraform/modules/identity/policies.tf

statement {
  sid    = "DenyRoleCreationWithoutBoundary"
  effect = "Deny"
  actions = ["iam:CreateRole"]
  resources = ["*"]
  condition {
    test     = "StringNotEquals"
    variable = "iam:PermissionsBoundary"
    # Garante que a nova role TENHA o boundary anexado no momento da criação
    values   = ["arn:aws:iam::${account_id}:policy/${project_name}-infra-boundary"]
  }
}
```

## 2. Segurança: Princípio do Menor Privilégio (Prioridade Alta)

**Vulnerabilidade:** Uso de wildcards (`iam:*`, `s3:*`) viola o princípio de _Least Privilege_ e dificulta auditoria.

**Correção:** Substituir permissões amplas por listas explícitas.

```hcl
# terraform/modules/identity/policies.tf

locals {
  required_iam_actions = [
    "iam:CreateRole", "iam:DeleteRole", "iam:GetRole",
    "iam:PutRolePermissionsBoundary", "iam:AttachRolePolicy",
    "iam:DetachRolePolicy", "iam:TagRole", "iam:PassRole"
  ]
}

statement {
  sid    = "IAMExplicitActions"
  effect = "Allow"
  actions = local.required_iam_actions
  resources = ["arn:aws:iam::*:role/${var.project_name}-*"]
}
```

## 3. Confiabilidade: Resiliência na CLI Go (Prioridade Média)

**Gap:** Falta de _retries_ e _timeouts_ nas chamadas AWS pode causar travamentos em operações de CI/CD.

**Correção:** Configurar o cliente AWS com `Retryer` e usar Contextos com Timeout.

```go
// cli/internal/utils/config.go
import "github.com/aws/aws-sdk-go-v2/aws/retry"

cfg, err := config.LoadDefaultConfig(context.TODO(),
    config.WithRegion(utils.GetRegion()),
    config.WithRetryer(func() aws.Retryer {
        return retry.AddWithMaxAttempts(retry.NewStandard(), 5) // Backoff exponencial
    }),
)

// Uso:
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()
out, err := svc.GetItem(ctx, ...)
```

## 4. Qualidade: Robustez em Scripts Bash (Prioridade Média) ✅ **RESOLVIDO**

**Armadilha:** Scripts sem `set -e` continuam executando após erros, podendo causar estados inconsistentes.

**Correção Implementada:** Migração completa para CLI Go (`aponte`) eliminou a dependência de scripts Bash. A CLI Go oferece tipagem forte e tratamento de erros nativo, eliminando os problemas de robustez dos scripts Bash.

**Status:** ✅ Todos os scripts Bash críticos foram migrados para a CLI Go em 2024. Scripts Python (`script_python/`) mantidos para orquestração e menu interativo seguem boas práticas de tratamento de erros.

## 5. Operabilidade: Desbloqueio de Testes (Prioridade Alta)

**Bloqueio:** `prevent_destroy = true` impede a limpeza de ambientes de teste automatizados.

**Correção:** Tornar a proteção condicional: `prevent_destroy = var.environment != "ephemeral"`.
