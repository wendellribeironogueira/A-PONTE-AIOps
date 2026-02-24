package cmd

import (
	"github.com/spf13/cobra"
)

// gitCmd represents the git command
var gitCmd = &cobra.Command{
	Use:   "git",
	Short: "Operações Git auxiliares",
	Long:  `Utilitários para clonar e sincronizar repositórios no contexto da plataforma.`,
}

func init() {
	rootCmd.AddCommand(gitCmd)
}
