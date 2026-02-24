package cmd

import (
	"fmt"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var cleanCmd = &cobra.Command{
	Use:   "clean",
	Short: "Limpa caches locais (.terragrunt-cache, .terraform)",
	Run:   runClean,
}

func init() {
	systemCmd.AddCommand(cleanCmd)
}

func runClean(cmd *cobra.Command, args []string) {
	if err := core.CleanCaches(); err != nil {
		fmt.Printf("❌ Erro na limpeza: %v\n", err)
	}
}
