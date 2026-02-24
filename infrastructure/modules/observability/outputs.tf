output "config_compliance_topic_arn" {
  description = "ARN do tópico SNS para conformidade do AWS Config"
  value       = var.create_global_resources ? aws_sns_topic.config_compliance[0].arn : null
}

output "main_dashboard_name" {
  description = "Nome do Dashboard principal do CloudWatch"
  value       = var.create_global_resources ? aws_cloudwatch_dashboard.main[0].dashboard_name : null
}
