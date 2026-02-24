terraform {
  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.2.0"
    }
  }
}

# ==============================================================================
# BREAK GLASS CLEANUP - Automação Server-Side
# Lambda responsável por limpar sessões expiradas e garantir revogação de acesso.
# ==============================================================================

variable "private_subnet_ids" {
  description = "List of private subnet IDs for the Lambda function to run in. If empty, VPC config is skipped."
  type        = list(string)
  default     = []
}

variable "lambda_security_group_id" {
  description = "The ID of the security group to associate with the Lambda function. If empty, VPC config is skipped."
  type        = string
  default     = ""
}

# --- Recursos de Suporte para a Lambda de Cleanup ---

resource "aws_sqs_queue" "break_glass_dlq" {
  count                   = var.create_global_resources ? 1 : 0
  name                    = lower("${var.project_name}-break-glass-cleanup-dlq")
  sqs_managed_sse_enabled = true # Habilita criptografia padrão gerenciada pela AWS
  tags                    = var.tags
}

data "archive_file" "break_glass_lambda" {
  type        = "zip"
  source_file = "${path.module}/src/break_glass_cleanup.py"
  output_path = "${path.module}/dist/break_glass_cleanup.zip"
}

resource "aws_lambda_function" "break_glass_cleanup" {
  count                          = var.create_global_resources ? 1 : 0
  function_name                  = lower("${var.project_name}-break-glass-cleanup")
  role                           = aws_iam_role.break_glass_lambda[0].arn
  handler                        = "break_glass_cleanup.handler"
  runtime                        = "python3.11"
  timeout                        = 60
  filename                       = data.archive_file.break_glass_lambda.output_path
  source_code_hash               = data.archive_file.break_glass_lambda.output_base64sha256
  reserved_concurrent_executions = 5 # CKV_AWS_115: Limit concurrency

  # CKV_AWS_116: Dead Letter Queue for failed invocations
  dead_letter_config {
    target_arn = aws_sqs_queue.break_glass_dlq[0].arn
  }

  # CKV_AWS_117: Conditionally run Lambda inside a VPC for network isolation
  dynamic "vpc_config" {
    for_each = length(var.private_subnet_ids) > 0 && var.lambda_security_group_id != "" ? [1] : []
    content {
      subnet_ids         = var.private_subnet_ids
      security_group_ids = [var.lambda_security_group_id]
    }
  }

  # CKV_AWS_50: Enable active tracing
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      REGISTRY_TABLE_NAME = "a-ponte-registry" # Acoplamento fraco com o nome padrão
    }
  }

  tags = var.tags
}

# --- CloudWatch Log Group (FinOps: Retention) ---

resource "aws_cloudwatch_log_group" "break_glass_cleanup" {
  count             = var.create_global_resources ? 1 : 0
  name              = "/aws/lambda/${lower("${var.project_name}-break-glass-cleanup")}"
  retention_in_days = 30
  tags              = var.tags
}

# --- IAM Role para a Lambda ---

data "aws_caller_identity" "current" {
  count = var.create_global_resources ? 1 : 0
}

data "aws_region" "current" {
  count = var.create_global_resources ? 1 : 0
}

data "aws_subnet" "first_private" {
  count = var.create_global_resources && length(var.private_subnet_ids) > 0 ? 1 : 0
  id    = var.private_subnet_ids[0]
}

# --- IAM Role e Política para a Lambda de Cleanup ---

resource "aws_iam_role" "break_glass_lambda" {
  count = var.create_global_resources ? 1 : 0
  name  = lower("${var.project_name}-break-glass-lambda-role")

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

data "aws_iam_policy_document" "break_glass_lambda" {
  count = var.create_global_resources ? 1 : 0

  # Permissão para a Lambda criar seu próprio log group.
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
    ]
    resources = ["arn:aws:logs:${data.aws_region.current[0].name}:${data.aws_caller_identity.current[0].account_id}:log-group:/aws/lambda/${aws_lambda_function.break_glass_cleanup[0].function_name}"]
  }

  # Permissões para a Lambda criar e escrever em seus streams de log.
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:${data.aws_region.current[0].name}:${data.aws_caller_identity.current[0].account_id}:log-group:/aws/lambda/${aws_lambda_function.break_glass_cleanup[0].function_name}:*:*"]
  }

  # Permissões para acesso ao DynamoDB
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:UpdateItem",
      "dynamodb:GetItem"
    ]
    resources = ["arn:aws:dynamodb:${data.aws_region.current[0].name}:${data.aws_caller_identity.current[0].account_id}:table/a-ponte-registry"]
  }

  # Permissões para rede VPC (condicional)
  dynamic "statement" {
    for_each = length(var.private_subnet_ids) > 0 && var.lambda_security_group_id != "" ? [1] : []
    # CKV_AWS_290: As permissões de VPC da Lambda exigem Resource='*'. A condição 'ec2:Vpc' mitiga o risco, restringindo a ação à VPC correta.
    content {
      effect = "Allow"
      actions = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DeleteNetworkInterface"
      ]
      resources = ["*"] # Obrigatório pela AWS, mas restringido pela condição abaixo
      condition {
        test     = "StringEquals"
        variable = "ec2:Vpc"
        values   = [data.aws_subnet.first_private[0].vpc_id]
      }
    }
  }

  # Permissões para a Dead Letter Queue (SQS)
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.break_glass_dlq[0].arn]
  }

  # Permissões para X-Ray
  # CKV_AWS_290: As permissões do X-Ray exigem Resource='*'. Esta é uma limitação conhecida e documentada da AWS.
  statement {
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords"
    ]
    resources = ["*"] # Obrigatório pela AWS
  }
}

resource "aws_iam_role_policy" "break_glass_lambda" {
  count  = var.create_global_resources ? 1 : 0
  name   = "break-glass-lambda-policy"
  role   = aws_iam_role.break_glass_lambda[0].id
  policy = data.aws_iam_policy_document.break_glass_lambda[0].json
}

# --- Exporta ARN para uso no Scheduler (CLI) ---

resource "aws_ssm_parameter" "break_glass_lambda_arn" {
  count       = var.create_global_resources ? 1 : 0
  name        = "/${var.project_name}/global/security/break_glass_lambda_arn"
  description = "ARN da Lambda de limpeza de Break Glass"
  type        = "SecureString"
  value       = aws_lambda_function.break_glass_cleanup[0].arn
  tags        = var.tags
}

# --- IAM Role para o EventBridge Scheduler ---

resource "aws_iam_role" "scheduler_role" {
  count = var.create_global_resources ? 1 : 0
  name  = lower("${var.project_name}-break-glass-scheduler-role")

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "scheduler_policy" {
  count = var.create_global_resources ? 1 : 0
  name  = "break-glass-scheduler-policy"
  role  = aws_iam_role.scheduler_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.break_glass_cleanup[0].arn
      }
    ]
  })
}

resource "aws_ssm_parameter" "scheduler_role_arn" {
  count       = var.create_global_resources ? 1 : 0
  name        = "/${var.project_name}/global/security/break_glass_scheduler_role_arn"
  description = "ARN da Role do EventBridge Scheduler para Break Glass"
  type        = "SecureString"
  value       = aws_iam_role.scheduler_role[0].arn
  tags        = var.tags
}
