package tools

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/utils"
)

// RunProwler executes the Prowler security auditing tool via Docker.
func RunProwler() error {
	root := utils.GetProjectRoot()
	fmt.Println("☁️  Executando Prowler (Cluster)...")

	composeFile := filepath.Join(root, "config", "containers", "docker-compose.yml")

	// Prowler roda na conta AWS inteira, mas usa as credenciais do container
	c := exec.Command("docker", "compose", "-f", composeFile, "run", "--rm", "mcp-terraform",
		"prowler", "aws")
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	return c.Run()
}
