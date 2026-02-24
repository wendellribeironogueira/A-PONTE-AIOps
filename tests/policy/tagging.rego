package custom.tagging

deny[msg] {
    resource := input.resource
    not resource.tags.Project

    msg := sprintf("Recurso '%s' (%s) não possui a tag 'Project' obrigatória.", [resource.name, resource.type])
}

deny[msg] {
    resource := input.resource
    resource.tags.Project == ""

    msg := sprintf("Recurso '%s' (%s) possui a tag 'Project' vazia.", [resource.name, resource.type])
}
