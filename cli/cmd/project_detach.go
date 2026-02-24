package cmd

import (
	"fmt"
	"os"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var projectDetachCmd = &cobra.Command{
	Use:   "detach [name]",
	Short: "Desvincula um projeto (remove configs locais)",
	Long:  `Remove os arquivos de configuração locais (.repos, .auto.tfvars, .project.yml) sem destruir a infraestrutura na AWS.`,
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		projectName := resolveProjectContext(args)
		runDetachProject(projectName)
	},
}

func init() {
	projectCmd.AddCommand(projectDetachCmd)
}

func runDetachProject(name string) {
	checkProjectAndExitIfHome(name, "project detach")

	// Confirmação Interativa
	if os.Getenv("FORCE_NON_INTERACTIVE") != "true" {
		fmt.Printf("\n⚠️  DETACH: Remove configs locais mantendo infraestrutura na AWS\n")
		fmt.Printf("  Isso vai deletar .repos, .auto.tfvars e .project.yml de '%s'\n\n", name)
		if !utils.ConfirmAction("Confirma detach? [s/N]:") {
			fmt.Println("❌ Operação cancelada.")
			return
		}
	}

	core.DetachProject(name)

	// Se estivermos no projeto que foi desvinculado, volta para home
	current, _ := core.GetPersistedContext()
	if current == name {
		core.SetContext("home")
		fmt.Println("✅ Contexto resetado para 'home'")
	}

	fmt.Printf("✅ Projeto desvinculado: %s\n", name)
}
