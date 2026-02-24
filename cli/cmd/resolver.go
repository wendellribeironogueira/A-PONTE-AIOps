package cmd

import (
	"log"

	"aponte/cli/internal/core"
)

// resolveProjectContext determines the project context to operate on.
// It follows the priority: command-line argument > Environment Variable > .current_project file.
func resolveProjectContext(args []string) string {
	if len(args) > 0 && args[0] != "" {
		return args[0]
	}

	// FIX: Usa core.GetContext() para respeitar a prioridade da ENV VAR (TF_VAR_project_name)
	// Isso garante consistência com a variável de ambiente.
	project, err := core.GetContext()
	if err != nil {
		log.Fatalf("❌ Erro ao resolver contexto: %v", err)
	}

	if project == "" {
		log.Fatalf("❌ Erro: Contexto do projeto está vazio. Selecione um projeto com 'aponte project switch' ou especifique um como argumento.")
	}
	return project
}

// checkProjectAndExitIfHome is a guardrail to prevent operations on the neutral 'home' context.
func checkProjectAndExitIfHome(project string, commandName string) {
	if project == "home" {
		log.Fatalf("❌ Ação bloqueada: O comando '%s' não pode ser executado no contexto 'home'.\n   👉 Selecione um projeto com 'aponte project switch [NOME_DO_PROJETO]'.", commandName)
	}
}
