package core

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"aponte/cli/internal/utils"
)

// GetRollbackVersions retorna uma lista ordenada de versões de backup disponíveis para um projeto.
func GetRollbackVersions(project string) ([]string, error) {
	root := utils.GetProjectRoot()
	backupRootDir := filepath.Join(root, ".aponte-versions", "files", project)

	if _, err := os.Stat(backupRootDir); os.IsNotExist(err) {
		return nil, nil
	}

	entries, err := os.ReadDir(backupRootDir)
	if err != nil {
		return nil, fmt.Errorf("erro ao ler diretório de versões: %w", err)
	}

	var versions []string
	for _, e := range entries {
		if e.IsDir() {
			versions = append(versions, e.Name())
		}
	}

	// Ordena do mais recente para o mais antigo
	sort.Sort(sort.Reverse(sort.StringSlice(versions)))
	return versions, nil
}

// PerformRollback restaura uma versão específica da configuração do projeto.
func PerformRollback(project, version string) error {
	root := utils.GetProjectRoot()
	backupRootDir := filepath.Join(root, ".aponte-versions", "files", project)
	selectedDir := filepath.Join(backupRootDir, version)

	var targetDir string
	if project == "a-ponte" {
		targetDir = filepath.Join(root, "infrastructure", "bootstrap")
	} else {
		targetDir = filepath.Join(root, "projects")
	}

	// Garante que o diretório do projeto existe
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return fmt.Errorf("erro ao criar diretório do projeto: %w", err)
	}

	fmt.Printf("\n🔄 Iniciando Rollback para versão: %s\n", version)
	restoredCount := 0

	err := filepath.WalkDir(selectedDir, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}

		relPath, err := filepath.Rel(selectedDir, path)
		if err != nil {
			return err
		}

		srcPath := path
		dstPath := filepath.Join(targetDir, relPath)

		// Garante que subdiretórios existam no destino
		if err := os.MkdirAll(filepath.Dir(dstPath), 0755); err != nil {
			return err
		}

		// SAFETY NET: Backup do estado atual antes de sobrescrever (Pre-Rollback)
		if _, err := os.Stat(dstPath); err == nil {
			if _, err := utils.VersionFile(dstPath, project, "pre_rollback_"+version); err != nil {
				fmt.Printf("⚠️  Falha ao criar backup de segurança para %s: %v\n", d.Name(), err)
			}
		}

		if err := utils.CopyFile(srcPath, dstPath); err != nil {
			fmt.Printf("❌ Falha ao restaurar %s: %v\n", d.Name(), err)
		} else {
			fmt.Printf("  ✅ Arquivo restaurado: %s\n", relPath)
			restoredCount++
		}
		return nil
	})

	if err != nil {
		return fmt.Errorf("erro durante o processo de rollback: %w", err)
	}

	if restoredCount > 0 {
		fmt.Println("\n✅ Rollback concluído com sucesso!")
		fmt.Println("👉 Execute 'aponte project list' ou 'aponte repo list' para verificar o estado restaurado.")
	} else {
		fmt.Println("\n⚠️  Nenhum arquivo foi restaurado (backup vazio?).")
	}

	return nil
}
