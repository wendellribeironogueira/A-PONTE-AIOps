package cmd

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var gitPushCmd = &cobra.Command{
	Use:   "push",
	Short: "Snapshot rápido (Add + Commit + Push)",
	Long: `Executa git add ., git commit com timestamp e git push origin main/master.
Se estiver dentro de um projeto, executa em todos os repositórios vinculados.`,
	Run: func(cmd *cobra.Command, args []string) {
		runGitPush()
	},
}

func init() {
	gitCmd.AddCommand(gitPushCmd)
}

func runGitPush() {
	project, _ := core.GetContext()
	root := utils.GetProjectRoot()

	// 1. Contexto Home (Comportamento Padrão)
	if project == "" || project == "home" {
		fmt.Println("📂 Contexto: home (Executando no diretório atual)")
		executeGitCycle(".")
		return
	}

	// 2. Contexto de Projeto
	fmt.Printf("🚀 Contexto de Projeto: %s\n", project)

	// Recupera lista de repositórios (Local ou Remoto)
	repos, err := getProjectRepos(project, root)
	if err != nil {
		log.Printf("⚠️  Erro ao listar repositórios: %v", err)
		return
	}

	if len(repos) == 0 {
		fmt.Println("⚠️  Nenhum repositório vinculado a este projeto.")
		return
	}

	// Itera e executa
	for _, repo := range repos {
		repoName := extractRepoName(repo)
		repoPath := filepath.Join(root, "projects", project, "repos", repoName)

		if _, err := os.Stat(repoPath); os.IsNotExist(err) {
			fmt.Printf("⚠️  Repositório %s não clonado localmente (Pulando...)\n", repoName)
			continue
		}

		fmt.Printf("\n📦 Repositório: %s\n", repoName)
		executeGitCycle(repoPath)
	}
}

func getProjectRepos(project, root string) ([]string, error) {
	// Tenta ler do arquivo local .repos
	reposFile := filepath.Join(root, "projects", project+".repos")
	content, err := os.ReadFile(reposFile)
	if err == nil {
		var repos []string
		lines := strings.Split(string(content), "\n")
		for _, line := range lines {
			line = strings.TrimSpace(line)
			if line != "" && !strings.HasPrefix(line, "#") {
				repos = append(repos, line)
			}
		}
		return repos, nil
	}

	// Fallback para DynamoDB
	return core.ListRepositories(project)
}

func extractRepoName(urlOrName string) string {
	parts := strings.Split(urlOrName, "/")
	name := parts[len(parts)-1]
	return strings.TrimSuffix(name, ".git")
}

func executeGitCycle(dir string) {
	fmt.Println("➕ Adicionando arquivos (git add .)...")
	cmdAdd := exec.Command("git", "add", ".")
	cmdAdd.Dir = dir
	cmdAdd.Stdout = os.Stdout
	cmdAdd.Stderr = os.Stderr
	if err := cmdAdd.Run(); err != nil {
		log.Printf("❌ Falha no git add em %s: %v", dir, err)
		return
	}

	timestamp := time.Now().Format("2006-01-02 15:04:05")
	msg := fmt.Sprintf("snapshot: %s (via aponte cli)", timestamp)
	fmt.Printf("💾 Commitando: '%s'...\n", msg)

	cmdCommit := exec.Command("git", "commit", "-m", msg)
	cmdCommit.Dir = dir
	// Commit pode falhar se não houver mudanças, não deve ser fatal
	cmdCommit.Run()

	fmt.Println("⬆️  Enviando para remoto (git push)...")
	cmdPush := exec.Command("git", "push")
	cmdPush.Dir = dir
	cmdPush.Stdout = os.Stdout
	cmdPush.Stderr = os.Stderr

	if err := cmdPush.Run(); err != nil {
		// 1. Tenta corrigir URL mascarada (******) injetando token
		if tryPushWithToken(dir) {
			fmt.Println("✅ Push realizado com sucesso (Token injetado).")
			return
		}

		fmt.Println("⚠️  Falha no push padrão. Tentando configurar upstream...")

		// Tenta detectar branch atual e configurar upstream automaticamente
		cmdBranch := exec.Command("git", "rev-parse", "--abbrev-ref", "HEAD")
		cmdBranch.Dir = dir
		out, errBranch := cmdBranch.Output()

		if errBranch == nil {
			branch := strings.TrimSpace(string(out))
			if branch != "" {
				cmdUpstream := exec.Command("git", "push", "--set-upstream", "origin", branch)
				cmdUpstream.Dir = dir
				cmdUpstream.Stdout = os.Stdout
				cmdUpstream.Stderr = os.Stderr
				if errUp := cmdUpstream.Run(); errUp != nil {
					log.Printf("❌ Falha definitiva no git push: %v", errUp)
				} else {
					fmt.Println("✅ Upstream configurado e código enviado!")
				}
			}
		} else {
			log.Printf("❌ Falha ao detectar branch para upstream: %v", err)
		}
	} else {
		fmt.Println("✅ Código sincronizado com sucesso!")
	}
}

func tryPushWithToken(dir string) bool {
	cmdRemote := exec.Command("git", "remote", "get-url", "origin")
	cmdRemote.Dir = dir
	out, err := cmdRemote.Output()
	if err != nil {
		return false
	}
	remoteURL := strings.TrimSpace(string(out))

	if strings.Contains(remoteURL, "******") {
		token := os.Getenv("GITHUB_TOKEN")
		if token == "" {
			token = os.Getenv("GH_TOKEN")
		}
		if token != "" {
			fmt.Println("🔒 Detectada URL mascarada. Usando GIT_ASKPASS para autenticação segura...")

			// Cria script temporário para responder ao prompt de senha do Git
			var askpassContent, ext string
			if runtime.GOOS == "windows" {
				ext = ".bat"
				// No Windows Batch, % é caractere especial, mas echo simples costuma funcionar para tokens básicos.
				askpassContent = fmt.Sprintf("@echo off\necho %s", escapeBatchString(token))
			} else {
				ext = ".sh"
				// FIX: Usa Heredoc com aspas simples (<<'EOF') para evitar interpolação de variáveis ($) ou quebra com aspas (")
				askpassContent = fmt.Sprintf("#!/bin/sh\ncat <<'EOF'\n%s\nEOF\n", strings.ReplaceAll(token, "'", "'\\''"))
			}

			tmpFile, err := os.CreateTemp("", "git-askpass-*"+ext)
			if err != nil {
				return false
			}
			defer os.Remove(tmpFile.Name())

			tmpFile.WriteString(askpassContent)
			tmpFile.Close()
			os.Chmod(tmpFile.Name(), 0700)

			// Executa git push sem expor o token na URL (args)
			cmdPush := exec.Command("git", "push")
			cmdPush.Dir = dir
			cmdPush.Stdout = os.Stdout
			cmdPush.Stderr = os.Stderr
			// Configura o Git para usar nosso script como provedor de credenciais
			cmdPush.Env = append(os.Environ(),
				fmt.Sprintf("GIT_ASKPASS=%s", tmpFile.Name()),
				"GIT_TERMINAL_PROMPT=0", // Falha se o askpass não funcionar, não trava
			)

			if err := cmdPush.Run(); err == nil {
				return true
			}
		}
	}
	return false
}

func escapeBatchString(s string) string {
	// Escape special characters for Windows Batch echo
	s = strings.ReplaceAll(s, "%", "%%")
	s = strings.ReplaceAll(s, "^", "^^")
	s = strings.ReplaceAll(s, "&", "^&")
	s = strings.ReplaceAll(s, "<", "^<")
	s = strings.ReplaceAll(s, ">", "^>")
	s = strings.ReplaceAll(s, "|", "^|")
	return s
}
