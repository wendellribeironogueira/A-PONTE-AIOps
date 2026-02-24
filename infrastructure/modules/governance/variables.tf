# =================================================================================
# Governance Variables
# =================================================================================

variable "project_name" {
  description = "Nome do projeto"
  type        = string
}

variable "tags" {
  description = "Tags padrão"
  type        = map(string)
}

variable "budget_limit" {
  description = "Limite mensal de gastos em USD"
  type        = string
  default     = "50"
}

variable "budget_emails" {
  description = "Lista de emails para receber alertas de faturamento"
  type        = list(string)
  default     = ["admin@example.com"]
}
