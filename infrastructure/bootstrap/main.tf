# ==============================================================================
# MÓDULOS
# ==============================================================================

module "global" {
  source = "../modules/global"

  tags = var.tags
}

module "identity" {
  source = "../modules/iam"

  project_name = var.project_name
  account_id   = var.account_id
  aws_region   = var.aws_region

  # Conecta o módulo de identidade ao provedor OIDC global
  oidc_provider_arn = module.global.oidc_provider_arn

  registry_table_arn      = module.global.registry_table_arn
  github_repos            = var.github_repos
  tags                    = var.tags
  create_break_glass_role = var.create_break_glass_role
}

module "storage" {
  source = "../modules/storage"

  project_name            = var.project_name
  create_global_resources = true
  tags                    = var.tags
}

module "observability" {
  source = "../modules/observability"

  project_name            = var.project_name
  tags                    = var.tags
  security_email          = var.security_email
  create_global_resources = true

  # Integração entre módulos (Wiring)
  audit_logs_bucket_name = module.storage.audit_logs_bucket_name
  config_bucket_name     = module.storage.config_bucket_name
  sns_topic_arn          = module.security.security_topic_arn

  # Recursos construídos por convenção
  cloudtrail_log_group_name = "/aws/cloudtrail/${lower(var.project_name)}"
  permissions_boundary_arn  = module.identity.permissions_boundary_arn
}

module "governance" {
  source = "../modules/governance"

  project_name  = var.project_name
  tags          = var.tags
  budget_emails = [var.security_email]
}

module "security" {
  source = "../modules/security"

  project_name            = var.project_name
  create_global_resources = true
  tags                    = var.tags
  security_email          = var.security_email
  registry_table_name     = module.global.registry_table_name
  audit_logs_bucket_name  = module.storage.audit_logs_bucket_name
  config_bucket_name      = module.storage.config_bucket_name
}
