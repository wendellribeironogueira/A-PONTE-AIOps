package cmd

import (
	"fmt"
	"os"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

var infraCmd = &cobra.Command{
	Use:   "infra",
	Short: "Gerencia a infraestrutura local (Docker Compose)",
	Long:  `Orquestra os containers da plataforma (Banco de Dados, IA, Sandbox) usando Docker Compose.`,
}

var infraUpCmd = &cobra.Command{
	Use:   "up",
	Short: "Sobe os containers da plataforma",
	Run:   runInfraUp,
}

var infraDownCmd = &cobra.Command{
	Use:   "down",
	Short: "Derruba os containers da plataforma",
	Run:   runInfraDown,
}

var infraResetCmd = &cobra.Command{
	Use:   "reset",
	Short: "Reseta o ambiente (Down + Up --force-recreate)",
	Run:   runInfraReset,
}

var infraBuildCmd = &cobra.Command{
	Use:   "build",
	Short: "Reconstrói o container Sandbox (MCP)",
	Run:   runInfraBuild,
}

var infraPruneCmd = &cobra.Command{
	Use:   "prune",
	Short: "Limpa recursos Docker não utilizados (Redes/Containers zumbis)",
	Run:   runInfraPrune,
}

func init() {
	rootCmd.AddCommand(infraCmd)
	infraCmd.AddCommand(infraUpCmd)
	infraCmd.AddCommand(infraDownCmd)
	infraCmd.AddCommand(infraResetCmd)
	infraCmd.AddCommand(infraBuildCmd)
	infraCmd.AddCommand(infraPruneCmd)

	// Flags de Profile
	infraUpCmd.Flags().StringP("profile", "p", "", "Ativa um perfil específico (ai, security, scraper)")
	infraResetCmd.Flags().StringP("profile", "p", "", "Ativa um perfil específico no reset")
}

func runInfraUp(cmd *cobra.Command, args []string) {
	manager := core.NewInfraManager()

	if err := manager.CheckDockerRunning(cmd.Context()); err != nil {
		fmt.Printf("❌ Erro: %v\n", err)
		fmt.Println("💡 Dica: Verifique se o Docker Desktop está rodando ou se você tem permissões (sudo).")
		os.Exit(1)
	}

	profile, _ := cmd.Flags().GetString("profile")
	if err := manager.Up(profile, args); err != nil {
		fmt.Printf("❌ %v\n", err)
		os.Exit(1)
	}
}

func runInfraDown(cmd *cobra.Command, args []string) {
	manager := core.NewInfraManager()
	if err := manager.Down(); err != nil {
		fmt.Printf("❌ %v\n", err)
		os.Exit(1)
	}
}

func runInfraReset(cmd *cobra.Command, args []string) {
	manager := core.NewInfraManager()
	profile, _ := cmd.Flags().GetString("profile")
	if err := manager.Reset(profile, args); err != nil {
		fmt.Printf("❌ %v\n", err)
		os.Exit(1)
	}
}

func runInfraBuild(cmd *cobra.Command, args []string) {
	manager := core.NewInfraManager()
	if err := manager.Build(); err != nil {
		fmt.Printf("❌ %v\n", err)
		os.Exit(1)
	}
}

func runInfraPrune(cmd *cobra.Command, args []string) {
	manager := core.NewInfraManager()
	if err := manager.Prune(); err != nil {
		fmt.Printf("❌ %v\n", err)
		os.Exit(1)
	}
}
