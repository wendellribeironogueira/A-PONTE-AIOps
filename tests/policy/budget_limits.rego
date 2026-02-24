package custom.budget

# Bloqueia instâncias EC2 muito grandes/caras
deny[msg] {
    resource := input.resource
    resource.type == "aws_instance"

    # Verifica o tipo da instância
    instance_type := resource.values.instance_type

    # Regra: Bloqueia qualquer coisa maior que xlarge (ex: 2xlarge, 4xlarge, metal)
    regex.match(".*[2-9]xlarge", instance_type)

    msg := sprintf("Instância '%s' usa tipo caro '%s'. Permitido no máximo *.xlarge.", [resource.name, instance_type])
}
