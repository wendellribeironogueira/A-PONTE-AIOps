package security

# Regra: VPC deve ter Flow Logs habilitados
deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_vpc"

    # Verifica se existe algum recurso aws_flow_log no plano
    not has_flow_log

    msg = sprintf("VPC '%s' detectada sem Flow Logs configurados. (VULN-NET-001)", [resource.address])
}

has_flow_log {
    resource := input.resource_changes[_]
    resource.type == "aws_flow_log"
}
