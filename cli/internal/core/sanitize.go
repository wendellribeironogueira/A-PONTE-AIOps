package core

import (
	"fmt"
	"os"
	"path/filepath"
	"time"

	"aponte/cli/internal/utils"
)

// SanitizeArtifacts move arquivos gerados pela IA e backups para uma pasta de versionamento.
func SanitizeArtifacts(project string) error {
	root := utils.GetProjectRoot()
	fmt.Printf("🧹 Organizando artefatos para o projeto: %s\n", project)

	ts := time.Now().Format("20060102-150405")
	targetDir := filepath.Join(root, ".aponte-versions", "ia_ops_artifacts", project, ts)

	// Padrões para buscar
	patterns := []string{
		filepath.Join(root, "terraform", "req_*.tf"),
		filepath.Join(root, "terraform", "*.bak"),
	}

	movedCount := 0
	createdDir := false

	for _, pattern := range patterns {
		matches, err := filepath.Glob(pattern)
		if err != nil {
			continue
		}

		for _, file := range matches {
			if !createdDir {
				if err := os.MkdirAll(targetDir, 0755); err != nil {
					return fmt.Errorf("falha ao criar diretório %s: %w", targetDir, err)
				}
				createdDir = true
			}

			dest := filepath.Join(targetDir, filepath.Base(file))
			if err := os.Rename(file, dest); err == nil {
				movedCount++
				fmt.Printf("   -> Movido: %s\n", filepath.Base(file))
			} else {
				fmt.Printf("   ❌ Falha ao mover %s: %v\n", filepath.Base(file), err)
			}
		}
	}

	if movedCount > 0 {
		fmt.Printf("✅ %d artefatos movidos para: .aponte-versions/ia_ops_artifacts/%s/%s\n", movedCount, project, ts)
	} else {
		fmt.Println("ℹ️  Nenhum artefato de IA ou backup encontrado.")
		if createdDir {
			if err := os.Remove(targetDir); err != nil {
				fmt.Printf("⚠️  Falha ao remover diretório vazio %s: %v\n", targetDir, err)
			}
		}
	}
	return nil
}
