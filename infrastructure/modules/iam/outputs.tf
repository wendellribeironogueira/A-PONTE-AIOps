output "github_actions_role_arn" {
  description = "ARN da Role IAM assumida pelo GitHub Actions (OIDC)"
  value       = aws_iam_role.github_actions.arn
}

output "permissions_boundary_arn" {
  description = "ARN da Policy de Permissions Boundary"
  value       = aws_iam_policy.boundary.arn
}

output "registry_access_policy_arn" {
  description = "ARN da política de acesso ao Registry (DynamoDB)"
  value       = aws_iam_policy.registry_access.arn
}

output "support_break_glass_role_arn" {
  description = "ARN da Role de Break Glass (se criada)"
  value       = var.create_break_glass_role ? aws_iam_role.support_break_glass[0].arn : null
}
