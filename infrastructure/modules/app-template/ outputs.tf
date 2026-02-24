output "app_data_bucket" {
  description = "Nome do bucket de dados da aplicação"
  value       = aws_s3_bucket.app_data.id
}

output "app_config_param" {
  description = "Nome do parâmetro SSM de configuração"
  value       = aws_ssm_parameter.app_config.name
}

output "github_actions_role_arn" {
  description = "ARN da Role IAM para CI/CD (Configurar no GitHub)"
  value       = module.identity.github_actions_role_arn
}

output "permissions_boundary_arn" {
  description = "ARN do Permissions Boundary aplicado"
  value       = module.identity.permissions_boundary_arn
}
