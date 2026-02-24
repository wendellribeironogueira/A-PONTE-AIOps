package core

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"aponte/cli/internal/utils"
)

// DetectDrift checks for infrastructure drift using Terraform plan.
// Returns true if drift is detected, false otherwise.
func DetectDrift(project string) (bool, error) {
	fmt.Printf("🔍 Verificando drift para: %s\n", project)

	if err := os.Setenv("TF_VAR_project_name", project); err != nil {
		return false, fmt.Errorf("erro ao definir TF_VAR_project_name: %w", err)
	}
	if err := os.Setenv("TF_VAR_aws_region", utils.GetRegion()); err != nil {
		return false, fmt.Errorf("erro ao definir TF_VAR_aws_region: %w", err)
	}

	root := utils.GetProjectRoot()
	relTfDir := getTfDir(project)
	tfDir := filepath.Join(root, relTfDir)

	if _, err := os.Stat(tfDir); os.IsNotExist(err) {
		return false, fmt.Errorf("diretório de infraestrutura não encontrado: %s\n   💡 Dica: O projeto '%s' possui arquivos Terraform?", tfDir, project)
	}

	// Executa plan com detailed-exitcode
	// 0 = Succeeded, diff is empty (no changes)
	// 1 = Error
	// 2 = Succeeded, there is a diff
	cmd := utils.ExecMCP(relTfDir, "terragrunt", "plan", "-detailed-exitcode", "-lock=false")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	err := cmd.Run()

	if err != nil {
		if exitError, ok := err.(*exec.ExitError); ok {
			code := exitError.ExitCode()
			if code == 2 {
				return true, nil
			}
		}
		return false, fmt.Errorf("erro ao executar plan: %w", err)
	}

	fmt.Println("\n✅ Nenhum drift detectado. A infraestrutura está sincronizada.")
	return false, nil
}

// FixDrift applies configuration to fix drift.
func FixDrift(project string) error {
	fmt.Printf("🛡️  Corrigindo drift para: %s\n", project)

	if err := os.Setenv("TF_VAR_project_name", project); err != nil {
		return fmt.Errorf("erro ao definir TF_VAR_project_name: %w", err)
	}
	if err := os.Setenv("TF_VAR_aws_region", utils.GetRegion()); err != nil {
		return fmt.Errorf("erro ao definir TF_VAR_aws_region: %w", err)
	}

	relTfDir := getTfDir(project)

	cmd := utils.ExecMCP(relTfDir, "terragrunt", "apply", "-auto-approve")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("falha ao corrigir drift: %w", err)
	}

	fmt.Println("\n✅ Drift corrigido. Infraestrutura sincronizada.")
	return nil
}
