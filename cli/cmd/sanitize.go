package cmd

import (
	"fmt"
	"os"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var sanitizeCmd = &cobra.Command{
	Use:   "sanitize",
	Short: "Organiza artefatos de IA e backups",
	Long:  `Move arquivos gerados pela IA (req_*.tf) e backups (.bak) para a pasta de versionamento (.aponte-versions).`,
	Run:   runSanitize,
}

func init() {
	systemCmd.AddCommand(sanitizeCmd)
}

func runSanitize(cmd *cobra.Command, args []string) {
	project, err := core.GetContext()
	if err != nil || project == "" {
		project = "home"
	}
	if err = core.SanitizeArtifacts(project); err != nil {
		fmt.Printf("❌ Erro ao organizar artefatos: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("✅ Artefatos organizados com sucesso.")
}
