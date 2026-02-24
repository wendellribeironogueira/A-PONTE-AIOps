package cmd

import (
	"fmt"
	"os"

	"aponte/cli/internal/docker"

	"github.com/spf13/cobra"
)

var systemCmd = &cobra.Command{
	Use:   "system",
	Short: "Gerenciamento do sistema e manutenção",
}

var systemHealCmd = &cobra.Command{
	Use:   "heal",
	Short: "Recuperação profunda do ambiente (Clean + Init)",
	Run:   runSystemHeal,
}

func init() {
	rootCmd.AddCommand(systemCmd)
	systemCmd.AddCommand(systemHealCmd)
}

func runSystemHeal(cmd *cobra.Command, args []string) {
	fmt.Println("🩹 Iniciando processo de cura (Deep Heal)...")

	client, err := docker.NewClient()
	if err != nil || !client.IsRunning(cmd.Context()) {
		fmt.Println("❌ Docker não está rodando! Inicie o Docker e tente novamente.")
		os.Exit(1)
	}

	// Reusa lógica interna dos comandos existentes
	runClean(cmd, args)
	runTfCommand("init", args, "-reconfigure")
}
