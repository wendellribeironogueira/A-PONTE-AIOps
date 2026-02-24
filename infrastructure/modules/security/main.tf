# ==============================================================================
# SERVICE DISCOVERY (SSM Parameter Store) - ADR-015
# Exporta recursos globais para consumo dinâmico pela CLI e Projetos
# ==============================================================================

resource "aws_ssm_parameter" "registry_table_name" {
  name        = "/${var.project_name}/global/dynamodb/registry_table_name"
  description = "Nome da tabela DynamoDB de registro de projetos (Single Source of Truth)"
  type        = "String"
  value       = var.registry_table_name
  tags        = var.tags
}

resource "aws_ssm_parameter" "audit_logs_bucket" {
  name        = "/${var.project_name}/global/s3/audit_logs_bucket_name"
  description = "Bucket central de logs de auditoria (CloudTrail)"
  type        = "String"
  value       = var.audit_logs_bucket_name
  tags        = var.tags
}

resource "aws_ssm_parameter" "config_bucket" {
  name        = "/${var.project_name}/global/s3/config_bucket_name"
  description = "Bucket central de logs do AWS Config"
  type        = "String"
  value       = var.config_bucket_name
  tags        = var.tags
}

resource "aws_ssm_parameter" "security_email" {
  name        = "/${var.project_name}/global/security/contact_email"
  description = "E-mail de contato de segurança da plataforma"
  type        = "String"
  value       = var.security_email
  tags        = var.tags
}

resource "aws_sns_topic" "security_alerts" {
  name = lower("${var.project_name}-security-alerts")
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.security_alerts.arn
  protocol  = "email"
  endpoint  = var.security_email
}

resource "aws_sns_topic_policy" "default" {
  arn = aws_sns_topic.security_alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = ["events.amazonaws.com", "cloudwatch.amazonaws.com"]
      }
      Action   = "SNS:Publish"
      Resource = aws_sns_topic.security_alerts.arn
    }]
  })
}
