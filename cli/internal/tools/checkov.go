package tools

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/utils"
)

// RunCheckov executes Checkov analysis on the specified directory.
func RunCheckov(tfDir string) error {
	root := utils.GetProjectRoot()
	fmt.Printf("🛡️  Iniciando Checkov no diretório: %s\n", tfDir)

	if err := os.MkdirAll(filepath.Join(root, "logs"), 0755); err != nil {
		return fmt.Errorf("falha ao criar diretório de logs: %w", err)
	}

	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	// 1. Relatório JSON (Background)
	fmt.Println("   - Gerando relatório JSON...")
	jsonFile, err := os.Create(filepath.Join(root, "logs", "checkov.json"))
	if err != nil {
		return fmt.Errorf("falha ao criar arquivo de log: %w", err)
	}
	defer func() { _ = jsonFile.Close() }()

	jsonCmd := exec.Command("docker", "compose", "-f", composeFile, "run", "--rm", "mcp-terraform",
		"checkov", "-d", tfDir,
		"--skip-path", ".terraform", "--skip-path", ".terragrunt-cache",
		"--skip-path", "venv", "--skip-path", "node_modules", "--skip-path", ".git",
		"--output", "json")
	jsonCmd.Stdout = jsonFile
	_ = jsonCmd.Run()

	// 2. Output Console (Interativo)
	fmt.Println("   - Exibindo resultados...")
	consoleCmd := exec.Command("docker", "compose", "-f", composeFile, "run", "--rm", "mcp-terraform",
		"checkov", "-d", tfDir,
		"--skip-path", ".terraform", "--skip-path", ".terragrunt-cache",
		"--skip-path", "venv", "--skip-path", "node_modules", "--skip-path", ".git",
		"--compact")
	consoleCmd.Stdout = os.Stdout
	consoleCmd.Stderr = os.Stderr

	return consoleCmd.Run()
}
