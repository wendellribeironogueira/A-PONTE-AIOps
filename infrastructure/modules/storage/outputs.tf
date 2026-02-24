output "audit_logs_bucket_name" {
  description = "Nome do bucket de logs de auditoria"
  value       = aws_s3_bucket.audit_logs.id
}

output "config_bucket_name" {
  description = "Nome do bucket de logs do AWS Config"
  value       = try(aws_s3_bucket.config[0].id, "")
}
