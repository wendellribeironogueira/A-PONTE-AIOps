package cmd

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"aponte/cli/internal/core"
	"aponte/cli/internal/git"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var gitCloneCmd = &cobra.Command{
	Use:   "clone [url]",
	Short: "Clona um repositório externo para o diretório atual ou projects/",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		var url string
		if len(args) > 0 {
			url = args[0]
		} else {
			fmt.Print("Digite a URL do repositório Git: ")
			reader := bufio.NewReader(os.Stdin)
			input, _ := reader.ReadString('\n')
			url = strings.TrimSpace(input)
		}
		runGitClone(url)
	},
}

func init() {
	gitCmd.AddCommand(gitCloneCmd)
}

func runGitClone(url string) {
	repoName := ""
	if url == "" {
		log.Fatal("❌ URL do repositório é obrigatória.")
	}

	if strings.HasSuffix(url, ".git") {
		parts := strings.Split(url, "/")
		repoName = strings.TrimSuffix(parts[len(parts)-1], ".git")
	} else {
		parts := strings.Split(url, "/")
		repoName = parts[len(parts)-1]
	}

	if repoName == "" {
		log.Fatal("❌ Não foi possível determinar o nome do repositório a partir da URL.")
	}

	root := utils.GetProjectRoot()
	project, _ := core.GetContext()
	cwd, _ := os.Getwd()

	var targetDir string

	// Se estiver em um contexto de projeto ativo, organiza o clone dentro dele
	if project != "" && project != "home" {
		targetDir = filepath.Join(root, "projects", project, "repos", repoName)
		os.MkdirAll(filepath.Dir(targetDir), 0755)
	} else if cwd == root {
		// Se estiver na raiz e sem contexto (home), assume que é um novo projeto
		targetDir = filepath.Join(root, "projects", repoName)
	} else {
		// Comportamento padrão do git (diretório atual)
		targetDir = repoName
	}

	fmt.Printf("⬇️  Clonando %s para %s...\n", url, targetDir)

	if err := git.Clone(url, targetDir); err != nil {
		log.Fatalf("❌ Falha ao clonar: %v", err)
	}

	fmt.Printf("✅ Repositório clonado com sucesso em: %s\n", targetDir)
	fmt.Println("💡 Dica: Use 'aponte repo add' para vinculá-lo a um projeto.")
}
