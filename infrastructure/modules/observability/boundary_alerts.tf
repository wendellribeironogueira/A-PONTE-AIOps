# =================================================================================
# Monitoramento de Segurança (Boundary Violations)
# =================================================================================

resource "aws_cloudwatch_log_metric_filter" "boundary_violation" {
  count          = var.create_global_resources ? 1 : 0
  name           = "${var.project_name}-boundary-violation"
  pattern        = "{ ($.errorCode = \"AccessDenied\") && (($.errorMessage = \"*explicit deny in a permissions boundary*\") || ($.errorMessage = \"*no permissions boundary allows*\")) }"
  log_group_name = aws_cloudwatch_log_group.cloudtrail[0].name

  depends_on = [aws_cloudwatch_log_group.cloudtrail]

  metric_transformation {
    name      = "BoundaryViolationCount"
    namespace = "Security/Identity"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "boundary_violation" {
  count               = var.create_global_resources ? 1 : 0
  alarm_name          = "${var.project_name}-boundary-violation-alarm"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = "1"
  metric_name         = "BoundaryViolationCount"
  namespace           = "Security/Identity"
  period              = "60"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "Alerta de Segurança: Uma ação foi bloqueada pelo Permissions Boundary (Tentativa de Escalação de Privilégio)."
  alarm_actions       = [var.sns_topic_arn]
  treat_missing_data  = "notBreaching"

  depends_on = [aws_cloudwatch_log_group.cloudtrail]
  tags       = var.tags
}
