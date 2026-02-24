package cmd

import (
	"github.com/spf13/cobra"
)

// repoCmd represents the repo command
var repoCmd = &cobra.Command{
	Use:   "repo",
	Short: "Gerencia repositórios vinculados",
	Long:  `Adiciona, remove e lista repositórios Git vinculados a um projeto.`,
}

func init() {
	rootCmd.AddCommand(repoCmd)
}
