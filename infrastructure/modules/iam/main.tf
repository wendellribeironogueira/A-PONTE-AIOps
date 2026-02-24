resource "aws_iam_role" "github_actions" {
  name                 = lower("${var.project_name}-github-actions-role")
  description          = "Role assumida pelo GitHub Actions via OIDC para o projeto ${var.project_name}"
  assume_role_policy   = data.aws_iam_policy_document.oidc_assume.json
  permissions_boundary = aws_iam_policy.boundary.arn

  # OPERABILIDADE: Permite destruir a role mesmo que existam policies anexadas.
  # Isso resolve o erro "DeleteConflict" durante a destruição de ambientes efêmeros.
  force_detach_policies = true

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "devops_policy_attachment" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.devops_policy.arn
}

# SEGURANÇA MULTI-TENANT:
# Anexa a política que restringe o acesso ao DynamoDB apenas às chaves deste projeto.
resource "aws_iam_role_policy_attachment" "registry_access_attachment" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.registry_access.arn
}

resource "aws_iam_policy" "devops_policy" {
  name        = lower("${var.project_name}-devops-policy")
  description = "Política de operações DevOps para ${var.project_name}"
  policy      = data.aws_iam_policy_document.devops_policy.json
  tags        = var.tags
}

resource "aws_iam_policy" "boundary" {
  name        = lower("${var.project_name}-infra-boundary")
  description = "Permissions Boundary que define o teto de permissoes para ${var.project_name}"
  policy      = data.aws_iam_policy_document.boundary.json
  tags        = var.tags
}

# ==============================================================================
# BREAK GLASS (Acesso de Emergência)
# ==============================================================================

resource "aws_iam_role" "support_break_glass" {
  count                = var.create_break_glass_role ? 1 : 0
  name                 = lower("${var.project_name}-support-break-glass")
  description          = "Role de emergencia (Break Glass) com privilegios elevados. Monitorada."
  permissions_boundary = aws_iam_policy.boundary.arn
  tags                 = merge(var.tags, { Type = "BreakGlass", Security = "Critical" })

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        AWS = "arn:aws:iam::${var.account_id}:root"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "support_admin" {
  count      = var.create_break_glass_role ? 1 : 0
  role       = aws_iam_role.support_break_glass[0].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# ==============================================================================
# BREAK GLASS AUTOMATION (ADR-007 Compliance)
# Infraestrutura para revogação automática de acesso
# ==============================================================================

data "archive_file" "lambda_zip" {
  count       = var.create_break_glass_role ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/lambda_break_glass.zip"

  source {
    content  = <<EOF
import boto3
import os

def handler(event, context):
    iam = boto3.client('iam')
    role_name = os.environ['TARGET_ROLE_NAME']
    print(f"Revogando acesso para: {role_name}")

    # Aplica uma política inline de DenyAll para neutralizar a role imediatamente
    deny_policy = '{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Action":"*","Resource":"*"}]}'
    iam.put_role_policy(RoleName=role_name, PolicyName='BreakGlassRevocation', PolicyDocument=deny_policy)
    print(f"Acesso revogado com sucesso (DenyAll aplicado).")
EOF
    filename = "index.py"
  }
}

resource "aws_iam_role" "lambda_exec" {
  count = var.create_break_glass_role ? 1 : 0
  name  = lower("${var.project_name}-break-glass-lambda-role")

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_lambda_function" "revoke_access" {
  count            = var.create_break_glass_role ? 1 : 0
  function_name    = lower("${var.project_name}-break-glass-revocation")
  handler          = "index.handler"
  runtime          = "python3.9"
  role             = aws_iam_role.lambda_exec[0].arn
  filename         = data.archive_file.lambda_zip[0].output_path
  source_code_hash = data.archive_file.lambda_zip[0].output_base64sha256
  timeout          = 60

  environment {
    variables = {
      TARGET_ROLE_NAME = aws_iam_role.support_break_glass[0].name
    }
  }
  tags = var.tags
}

# SEGURANÇA OPERACIONAL:
# Permite que a Lambda de limpeza realmente revogue o acesso da role de suporte.
resource "aws_iam_role_policy" "lambda_exec_policy" {
  count = var.create_break_glass_role ? 1 : 0
  name  = "break-glass-revocation-policy"
  role  = aws_iam_role.lambda_exec[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "iam:PutRolePolicy"
        Resource = aws_iam_role.support_break_glass[0].arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${aws_lambda_function.revoke_access[0].function_name}"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/lambda/${aws_lambda_function.revoke_access[0].function_name}:*"
      }
    ]
  })
}

# Nota: O EventBridge Scheduler (Trigger) é criado dinamicamente pela CLI
# no momento da solicitação de acesso, apontando para esta Lambda.
