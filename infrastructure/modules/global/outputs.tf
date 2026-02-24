output "oidc_provider_arn" {
  description = "ARN do provedor OIDC do GitHub, para ser usado por módulos de tenant."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "registry_table_arn" {
  description = "ARN da tabela de registro de projetos."
  value       = aws_dynamodb_table.registry.arn
}

output "registry_table_name" {
  description = "Nome da tabela de registro de projetos."
  value       = aws_dynamodb_table.registry.name
}
