output "budget_name" {
  description = "Nome do orçamento criado"
  value       = aws_budgets_budget.cost_budget.name
}
