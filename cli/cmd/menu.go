package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

// menuCmd represents the menu command
var menuCmd = &cobra.Command{
	Use:   "menu",
	Short: "Abre o menu interativo",
	Run:   runMenu,
}

func init() {
	rootCmd.AddCommand(menuCmd)
}

func runMenu(cmd *cobra.Command, args []string) {
	root := utils.GetProjectRoot()
	// FIX: Caminho corrigido para v2.0 (sem pasta tui)
	script := filepath.Join(root, "core", "tools", "menu.py")

	if _, err := os.Stat(script); os.IsNotExist(err) {
		fmt.Printf("❌ Erro: Script do menu não encontrado em: %s\n", script)
		os.Exit(1)
	}

	c := exec.Command(getPythonBinary(), script)

	// FIX: ADR-027 - Isolamento de Contexto via Override de Memória
	// ATUALIZAÇÃO: Respeita o contexto persistido se existir, senão usa home.
	ctx := "home"
	if savedCtx, err := core.GetPersistedContext(); err == nil && savedCtx != "" {
		ctx = savedCtx
	}

	// FIX: Usa injectProjectEnv para garantir consistência total de contexto (DRY)
	// Carrega metadados se possível para injetar ambiente correto (dev/prod)
	projData, _ := core.GetProject(ctx)
	injectProjectEnv(ctx, projData)
	c.Env = getPythonEnv(root)

	c.Stdin = os.Stdin
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr

	if err := c.Run(); err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			os.Exit(exitError.ExitCode())
		}
		fmt.Printf("❌ Erro na execução: %v\n", err)
		os.Exit(1)
	}
}
