package cmd

import (
	"github.com/spf13/cobra"
)

var projectCmd = &cobra.Command{
	Use:   "project",
	Short: "Gerencia projetos (Create, List, Switch)",
}

func init() {
	rootCmd.AddCommand(projectCmd)
}
