package core

import (
	"fmt"
	"os"
	"path/filepath"

	"aponte/cli/internal/utils"
)

// CleanCaches removes local cache directories (.terragrunt-cache, .terraform).
func CleanCaches() error {
	root := utils.GetProjectRoot()
	fmt.Printf("🧹 Iniciando limpeza em: %s\n", root)

	targets := []string{".terragrunt-cache", ".terraform"}
	count := 0

	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Ignora erros de permissão em subpastas
		}

		if info.IsDir() {
			// Otimização: Ignora pastas pesadas
			if info.Name() == "node_modules" || info.Name() == "venv" || info.Name() == ".git" || info.Name() == ".aponte-versions" {
				return filepath.SkipDir
			}

			for _, target := range targets {
				if info.Name() == target {
					fmt.Printf("Removing: %s\n", path)
					if err := os.RemoveAll(path); err != nil {
						fmt.Printf("⚠️  Falha ao remover %s: %v\n", path, err)
					} else {
						count++
					}
					return filepath.SkipDir
				}
			}
		}
		return nil
	})

	if err != nil {
		return fmt.Errorf("erro durante a varredura: %w", err)
	}

	fmt.Printf("✅ Limpeza concluída: %d pastas de cache removidas.\n", count)
	return nil
}
