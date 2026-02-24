package cmd

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"

	"aponte/cli/internal/core"

	"github.com/spf13/cobra"
)

// rollbackCmd represents the rollback command
var rollbackCmd = &cobra.Command{
	Use:   "rollback [project]",
	Short: "Restaura versões anteriores de arquivos de configuração",
	Long: `Permite visualizar e restaurar backups de arquivos de configuração (.project.yml, .repos, .tfvars)
armazenados no diretório de versionamento (.aponte-versions).

Cria automaticamente um backup de segurança do estado atual antes de aplicar o rollback (Safety Net).`,
	Args: cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		project := resolveProjectContext(args)
		runRollback(project)
	},
}

func init() {
	rootCmd.AddCommand(rollbackCmd)
}

func runRollback(project string) {
	checkProjectAndExitIfHome(project, "rollback")

	versions, err := core.GetRollbackVersions(project)
	if err != nil {
		fmt.Printf("❌ Erro ao listar versões: %v\n", err)
		return
	}

	if len(versions) == 0 {
		fmt.Printf("❌ Nenhum backup encontrado para o projeto '%s'.\n", project)
		return
	}

	fmt.Printf("\n🕰️  Histórico de Versões para '%s':\n", project)
	for i, v := range versions {
		// Formata para ficar mais legível (ex: 20231027-100000_user_reason)
		display := v
		parts := strings.SplitN(v, "_", 3)

		if len(parts) >= 2 && len(parts[0]) == 15 {
			ts := parts[0]
			var user, reason string

			if len(parts) == 3 {
				user = parts[1]
				reason = parts[2]
			} else {
				user = "legacy"
				reason = parts[1]
			}
			// 20060102-150405
			display = fmt.Sprintf("%s-%s-%s %s:%s:%s (%s) [%s]",
				ts[0:4], ts[4:6], ts[6:8], ts[9:11], ts[11:13], ts[13:15], user, reason)
		}
		fmt.Printf("  %d) %s\n", i+1, display)
	}

	// 2. Interação com Usuário
	fmt.Print("\nSelecione o número da versão para restaurar (0 para cancelar): ")
	reader := bufio.NewReader(os.Stdin)
	input, _ := reader.ReadString('\n')
	input = strings.TrimSpace(input)

	selection, err := strconv.Atoi(input)
	if err != nil || selection < 1 || selection > len(versions) {
		if input != "0" {
			fmt.Println("❌ Seleção inválida.")
		} else {
			fmt.Println("❌ Operação cancelada.")
		}
		return
	}

	selectedVersion := versions[selection-1]

	// 3. Restauração via Core
	if err := core.PerformRollback(project, selectedVersion); err != nil {
		fmt.Printf("❌ %v\n", err)
		os.Exit(1)
	}
}
