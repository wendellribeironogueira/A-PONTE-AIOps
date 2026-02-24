package cmd

import (
	"github.com/spf13/cobra"
)

var driftReportCmd = &cobra.Command{
	Use:   "report [project]",
	Short: "Gera relatório de drift (Alias para detect)",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		// Reusa a lógica de detect
		driftDetectCmd.Run(cmd, args)
	},
}

func init() {
	driftCmd.AddCommand(driftReportCmd)
}
