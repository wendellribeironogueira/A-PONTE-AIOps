package tools

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/utils"
)

// RunTfsec executes TFSec analysis on the specified directory.
func RunTfsec(tfDir string) error {
	root := utils.GetProjectRoot()
	fmt.Printf("🛡️  Executando TFSec em %s...\n", tfDir)

	if err := os.MkdirAll(filepath.Join(root, "logs"), 0755); err != nil {
		return fmt.Errorf("falha ao criar diretório de logs: %w", err)
	}

	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	// JSON Output (Background)
	_ = exec.Command("docker", "compose", "-f", composeFile, "run", "--rm", "mcp-terraform",
		"tfsec", tfDir, "--format", "json", "--out", "logs/tfsec.json", "--soft-fail", "--ignore-hcl-errors").Run()

	// Console Output (Interactive)
	c := exec.Command("docker", "compose", "-f", composeFile, "run", "--rm", "mcp-terraform",
		"tfsec", tfDir, "--soft-fail", "--ignore-hcl-errors")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	return c.Run()
}
