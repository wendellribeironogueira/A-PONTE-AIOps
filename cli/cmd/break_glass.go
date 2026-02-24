package cmd

import (
	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var breakGlassCmd = &cobra.Command{
	Use:   "break-glass",
	Short: "Gerencia acesso de emergência (Break Glass)",
	Long:  `Permite elevar privilégios temporariamente em caso de emergência, emitindo credenciais de curta duração.`,
}

var breakGlassEnableCmd = &cobra.Command{
	Use:   "enable [project]",
	Short: "Ativa o modo de emergência",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		project := resolveProjectContext(args)
		runBreakGlassEnable(project)
	},
}

var breakGlassDisableCmd = &cobra.Command{
	Use:   "disable [project]",
	Short: "Desativa o modo de emergência e restaura OIDC",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		project := resolveProjectContext(args)
		runBreakGlassDisable(project)
	},
}

func init() {
	rootCmd.AddCommand(breakGlassCmd)
	breakGlassCmd.AddCommand(breakGlassEnableCmd)
	breakGlassCmd.AddCommand(breakGlassDisableCmd)
}

func runBreakGlassEnable(project string) {
	checkProjectAndExitIfHome(project, "break-glass enable")
	core.EnableBreakGlass(project)
}

func runBreakGlassDisable(project string) {
	checkProjectAndExitIfHome(project, "break-glass disable")
	core.DisableBreakGlass(project)
}
