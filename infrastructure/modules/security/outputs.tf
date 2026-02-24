output "security_topic_arn" {
  description = "ARN do tópico SNS de alertas de segurança"
  value       = aws_sns_topic.security_alerts.arn
}
