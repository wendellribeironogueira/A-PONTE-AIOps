package tools

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/utils"
)

// RunTrivy executes Trivy scan on the specified directory.
func RunTrivy(tfDir string) error {
	root := utils.GetProjectRoot()
	fmt.Printf("🛡️  Executando Trivy em %s...\n", tfDir)

	if err := os.MkdirAll(filepath.Join(root, "logs"), 0755); err != nil {
		return fmt.Errorf("falha ao criar diretório de logs: %w", err)
	}

	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	c := exec.Command("docker", "compose", "-f", composeFile, "run", "--rm", "mcp-terraform",
		"trivy", "fs", tfDir, "--skip-dirs", "venv,node_modules,.terraform,.aponte-versions",
		"--timeout", "15m", "--scanners", "vuln,secret")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	return c.Run()
}
