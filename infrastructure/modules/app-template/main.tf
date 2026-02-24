# Template Base para Aplicações A-PONTE
# Inclui recursos padrão que todo projeto precisa (State, Config, Storage)

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_ssm_parameter" "app_config" {
  name        = "/${var.project_name}/${var.environment}/app/config"
  description = "Configuração base para ${var.project_name}"
  type        = "String"
  value       = "initialized"
  tags        = var.tags
}

# Persiste o contato de segurança para uso operacional (ex: scripts de notificação)
resource "aws_ssm_parameter" "contact_email" {
  name        = "/${var.project_name}/${var.environment}/app/contact_email"
  description = "E-mail do responsável pelo projeto"
  type        = "String"
  value       = var.security_email
  tags        = var.tags
}

resource "aws_s3_bucket" "app_data" {
  bucket = lower("${var.project_name}-${var.environment}-data-${data.aws_caller_identity.current.account_id}")
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "app_data" {
  bucket = aws_s3_bucket.app_data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "app_data" {
  bucket = aws_s3_bucket.app_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "app_data" {
  bucket = aws_s3_bucket.app_data.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app_data" {
  bucket = aws_s3_bucket.app_data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ==============================================================================
# OBSERVABILIDADE & LOGS (Global Tables)
# ==============================================================================
module "observability" {
  source = "/app/infrastructure/modules/observability"

  project_name            = var.project_name
  create_global_resources = var.project_name == "a-ponte"
  tags                    = var.tags

  security_email            = var.security_email
  permissions_boundary_arn  = module.identity.permissions_boundary_arn
  audit_logs_bucket_name    = "${var.project_name}-audit-logs-${data.aws_caller_identity.current.account_id}"
  config_bucket_name        = "${var.project_name}-config-${data.aws_caller_identity.current.account_id}"
  cloudtrail_log_group_name = "aws-cloudtrail-logs-${var.project_name}"
  sns_topic_arn             = "arn:aws:sns:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:${var.project_name}-alerts"
}

# ==============================================================================
# GOVERNANÇA DE IDENTIDADE (CI/CD)
# Cria a Role exclusiva deste projeto para o GitHub Actions
# ==============================================================================
module "identity" {
  source = "/app/infrastructure/modules/iam"

  project_name = var.project_name
  account_id   = data.aws_caller_identity.current.account_id
  aws_region   = data.aws_region.current.id
  github_repos = var.github_repos
  tags         = var.tags

  # Conecta aos recursos globais do Core (A-PONTE)
  oidc_provider_arn  = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
  registry_table_arn = "arn:aws:dynamodb:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:table/a-ponte-registry"
}

# ==============================================================================
# AUTO-REGISTRO (Service Discovery)
# Garante que o projeto exista na tabela global de registro
# ==============================================================================
resource "aws_dynamodb_table_item" "registry" {
  depends_on = [module.identity]
  table_name = "a-ponte-registry"
  hash_key   = "ProjectName"

  item = <<ITEM
{
  "ProjectName": {"S": "${var.project_name}"},
  "Environment": {"S": "${var.environment}"},
  "Status": {"S": "ACTIVE"},
  "CreatedAt": {"S": "${timestamp()}"},
  "ManagedBy": {"S": "Terraform"}
}
ITEM

  lifecycle {
    ignore_changes = [item]
  }
}
