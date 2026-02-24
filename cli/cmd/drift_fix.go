//go:build ignore

package cmd

import (
	"log"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var driftFixCmd = &cobra.Command{
	Use:   "fix [project]",
	Short: "Corrige drift aplicando a configuração do código",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		project := resolveProjectContext(args)
		runDriftFix(project)
	},
}

func init() {
	driftCmd.AddCommand(driftFixCmd)
}

func runDriftFix(project string) {
	checkProjectAndExitIfHome(project, "drift fix")

	if err := core.FixDrift(project); err != nil {
		log.Fatalf("❌ %v", err)
	}
}
