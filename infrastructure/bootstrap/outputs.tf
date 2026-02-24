# =================================================================================
# Outputs de Governança
# =================================================================================

output "audit_logs_bucket" {
  description = "Bucket S3 central para logs de auditoria (CloudTrail/Access Logs)"
  value       = module.storage.audit_logs_bucket_name
}

output "config_logs_bucket" {
  description = "Bucket S3 para logs do AWS Config"
  value       = module.storage.config_bucket_name
}

output "permissions_boundary_arn" {
  description = "ARN do Permissions Boundary para governança (Configurar em Secrets: PERMISSIONS boundary_arn)"
  value       = module.identity.permissions_boundary_arn
}

output "github_actions_role_arn" {
  description = "ARN da Role OIDC para CI/CD (Configurar em Variables: ROLE_ARN)"
  value       = module.identity.github_actions_role_arn
}

output "support_break_glass_role_arn" {
  description = "ARN da Role de Break Glass"
  value       = module.identity.support_break_glass_role_arn
}

output "setup_instructions" {
  description = "Instruções para configuração do GitHub Actions"
  value       = <<EOT

🎉 Infraestrutura Base (Bootstrap) concluída com sucesso!

Para habilitar o CI/CD (GitHub Actions), configure as seguintes variáveis no seu repositório:

SECRETS:
- AWS_ACCOUNT_ID: ${var.account_id}

VARIABLES:
- AWS_REGION: ${var.aws_region}
- ROLE_ARN: ${module.identity.github_actions_role_arn}
- PERMISSIONS_BOUNDARY_ARN: ${module.identity.permissions_boundary_arn}
- TF_STATE_BUCKET: a-ponte-central-tfstate-${var.account_id}
- TF_LOCK_TABLE: a-ponte-lock-${var.project_name}

DASHBOARD DE OBSERVABILIDADE:
https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${module.observability.main_dashboard_name}

👉 Próximo passo: A automação de setup do GitHub será iniciada agora...
EOT
}
