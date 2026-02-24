package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/spf13/cobra"
)

// installCmd represents the install command
var installCmd = &cobra.Command{
	Use:   "install",
	Short: "Configura o acesso global à CLI A-PONTE",
	Long: `Instala um wrapper no perfil do seu shell (.bashrc/.zshrc/PowerShell) para permitir
que o comando 'aponte' seja executado de qualquer diretório.

Funcionalidades:
  - Detecção automática da raiz do projeto (via Makefile ou go.mod)
  - Configuração da variável APONTE_ROOT
  - Suporte a ambientes híbridos (Linux, MacOS, Windows + WSL)
  - Injeção de variáveis de ambiente (.env) e credenciais`,
	Run: func(cmd *cobra.Command, args []string) {
		if err := runInstall(); err != nil {
			fmt.Printf("❌ Erro na instalação: %v\n", err)
			os.Exit(1)
		}
	},
}

func init() {
	rootCmd.AddCommand(installCmd)
}

func runInstall() error {
	// 1. Identificar o diretório raiz do projeto
	// Tenta localizar baseado na posição do executável
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("falha ao obter caminho do executável: %w", err)
	}

	exePath, err = filepath.EvalSymlinks(exePath)
	if err != nil {
		return fmt.Errorf("falha ao resolver symlinks: %w", err)
	}

	// Assume que o binário está em <ROOT>/bin/aponte
	binDir := filepath.Dir(exePath)
	projectRoot := filepath.Dir(binDir)

	// Validação de sanidade (verifica se Makefile existe na raiz deduzida)
	// ATUALIZAÇÃO: Verifica Makefile OU go.mod para ser mais flexível
	if _, err := os.Stat(filepath.Join(projectRoot, "Makefile")); os.IsNotExist(err) {
		// Fallback: Tenta usar o diretório atual (útil para 'go run main.go')
		cwd, _ := os.Getwd()
		if _, err := os.Stat(filepath.Join(cwd, "go.mod")); err == nil {
			projectRoot = cwd
		} else {
			fmt.Println("⚠️  Aviso: Makefile/go.mod não encontrado na raiz. Assumindo estrutura baseada na localização do binário.")
		}
	}

	projectRoot, _ = filepath.Abs(projectRoot)
	// FIX: Normaliza para barras normais para evitar escape de aspas no Windows (ex: "C:\" -> "C:/")
	projectRoot = filepath.ToSlash(projectRoot)
	fmt.Printf("📂 Raiz do projeto detectada: %s\n", projectRoot)

	// Detecção de ambiente misto (WSL rodando binário Windows)
	if runtime.GOOS == "windows" && os.Getenv("WSL_DISTRO_NAME") != "" {
		fmt.Println("\n⚠️  AVISO: Você está executando o binário Windows (aponte.exe) dentro do WSL.")
		fmt.Println("   A instalação configurará o perfil do Windows (PowerShell), e NÃO o do WSL (Bash).")
		fmt.Println("   Isso explica por que o comando 'aponte' no WSL continua com o erro antigo/legado.")
		fmt.Println("   👉 Solução: Recompile para Linux e reinstale:")
		fmt.Println("      GOOS=linux go build -o bin/aponte ./cli && ./bin/aponte install")
		fmt.Println("")
	}

	// 2. Detectar Shell e Arquivo de Configuração
	var rcFile string
	var wrapperContent string
	homeDir, _ := os.UserHomeDir()

	if runtime.GOOS == "windows" {
		// Tenta localizar o perfil do PowerShell
		// Caminho padrão: Documents\PowerShell\Microsoft.PowerShell_profile.ps1
		// Ou Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1
		psDir := filepath.Join(homeDir, "Documents", "PowerShell")
		if _, err := os.Stat(psDir); os.IsNotExist(err) {
			psDir = filepath.Join(homeDir, "Documents", "WindowsPowerShell")
		}
		// Garante que o diretório existe
		os.MkdirAll(psDir, 0755)
		rcFile = filepath.Join(psDir, "Microsoft.PowerShell_profile.ps1")

		wrapperContent = fmt.Sprintf(`
# --- A-PONTE CLI START ---
$env:APONTE_ROOT = "%s"
$env:APONTE_SESSION_ID = $PID
function aponte {
    
    if ($args.Count -eq 0) {
        $old_ctx = $env:TF_VAR_project_name
        try {
            $env:TF_VAR_project_name = "home"
            & "$env:APONTE_ROOT/bin/aponte.exe" menu
        } finally {
            $env:TF_VAR_project_name = $old_ctx
        }
    } else {
        # FIX: Usa forward slash para consistência com filepath.ToSlash usado no APONTE_ROOT
        & "$env:APONTE_ROOT/bin/aponte.exe" @args
    }
}
# --- A-PONTE CLI END ---
`, projectRoot)

	} else {
		// Linux/Mac (Bash/Zsh)
		shell := os.Getenv("SHELL")
		if strings.Contains(shell, "zsh") {
			rcFile = filepath.Join(homeDir, ".zshrc")
		} else {
			rcFile = filepath.Join(homeDir, ".bashrc")
		}

		wrapperContent = fmt.Sprintf(`
# --- A-PONTE CLI START ---
export APONTE_ROOT="%s"
export APONTE_SESSION_ID="$$"
aponte() {
    if [ "$#" -eq 0 ]; then
        TF_VAR_project_name="home" "$APONTE_ROOT/bin/aponte" menu
    else
        "$APONTE_ROOT/bin/aponte" "$@"
    fi
}
# --- A-PONTE CLI END ---
`, projectRoot)
	}

	// 3. Limpeza e Instalação (Idempotência)
	// Lê o arquivo para remover definições antigas antes de escrever a nova
	contentBytes, err := os.ReadFile(rcFile)
	if err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("erro ao ler %s: %w", rcFile, err)
	}
	content := string(contentBytes)

	startMarker := "# --- A-PONTE CLI START ---"
	endMarker := "# --- A-PONTE CLI END ---"

	// Remove bloco antigo se existir (limpeza de lixo/legado)
	if idxStart := strings.Index(content, startMarker); idxStart != -1 {
		if idxEnd := strings.Index(content, endMarker); idxEnd != -1 {
			endPos := idxEnd + len(endMarker)
			if endPos > idxStart {
				fmt.Println("🧹 Removendo configuração legada...")
				content = content[:idxStart] + content[endPos:]
			}
		}
	}

	content = strings.TrimSpace(content)
	newContent := content + "\n\n" + wrapperContent

	fmt.Printf("🔄 Atualizando configuração em %s...\n", rcFile)

	if err := os.WriteFile(rcFile, []byte(newContent), 0644); err != nil {
		return fmt.Errorf("erro ao escrever em %s: %w", rcFile, err)
	}

	fmt.Printf("✅ Configuração adicionada ao %s\n", rcFile)
	fmt.Println("\n🎉 Instalação concluída!")
	if runtime.GOOS == "windows" {
		fmt.Printf("👉 Reinicie seu PowerShell ou execute: . $PROFILE\n")
	} else {
		fmt.Printf("👉 Execute: source %s\n", rcFile)
	}
	return nil
}
