package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var projectValidateCmd = &cobra.Command{
	Use:   "validate [name]",
	Short: "Valida a integridade estrutural do projeto",
	Long:  `Verifica se os arquivos de configuração essenciais (.project.yml, .repos, terragrunt.hcl) existem e estão acessíveis.`,
	Args:  cobra.MaximumNArgs(1),
	Run:   runProjectValidate,
}

func init() {
	projectCmd.AddCommand(projectValidateCmd)
}

func runProjectValidate(cmd *cobra.Command, args []string) {
	project := resolveProjectContext(args)
	checkProjectAndExitIfHome(project, "project validate")

	fmt.Printf("🔍 Validando integridade do projeto: %s\n", project)

	root := utils.GetProjectRoot()
	// FIX: Usa resolveTfDir para garantir o caminho correto (suporte a core/legacy)
	projectDir := filepath.Join(root, resolveTfDir(project))

	if _, err := os.Stat(projectDir); os.IsNotExist(err) {
		fmt.Printf("❌ Erro Crítico: Diretório do projeto não encontrado em %s\n", projectDir)
		os.Exit(1)
	}

	// Lista de arquivos obrigatórios para um projeto saudável
	requiredFiles := []string{
		project + ".project.yml",
		project + ".repos",
		project + ".auto.tfvars",
		"terragrunt.hcl",
	}

	hasErrors := false
	for _, f := range requiredFiles {
		path := filepath.Join(projectDir, f)
		if _, err := os.Stat(path); os.IsNotExist(err) {
			fmt.Printf("   ❌ Ausente: %s\n", f)
			hasErrors = true
		} else {
			fmt.Printf("   ✅ OK: %s\n", f)
		}
	}

	if hasErrors {
		fmt.Println("\n⚠️  O projeto possui arquivos de configuração ausentes. Tente rodar 'aponte project sync' ou 'aponte repo sync'.")
		os.Exit(1)
	}
	fmt.Println("\n✅ Projeto íntegro.")
}
