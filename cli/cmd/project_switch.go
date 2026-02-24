package cmd

import (
	"bufio"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"

	"aponte/cli/internal/core"
	"aponte/cli/internal/validator"

	"github.com/spf13/cobra"
)

var projectSwitchCmd = &cobra.Command{
	Use:   "switch [name]",
	Short: "Alterna para um projeto existente",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		var name string
		if len(args) > 0 {
			name = args[0]
		} else {
			// Modo Interativo: Lista projetos para seleção
			projects, err := core.ListProjects()
			if err != nil {
				log.Fatalf("❌ Erro ao listar projetos: %v", err)
			}

			if len(projects) == 0 {
				fmt.Println("❌ Nenhum projeto encontrado.")
				return
			}

			fmt.Println("Selecione o projeto:")
			for i, p := range projects {
				fmt.Printf("  %d) %s (%s)\n", i+1, p.Name, p.Environment)
			}
			fmt.Print("Opção: ")

			reader := bufio.NewReader(os.Stdin)
			input, _ := reader.ReadString('\n')
			input = strings.TrimSpace(input)

			idx, err := strconv.Atoi(input)
			if err != nil || idx < 1 || idx > len(projects) {
				log.Fatal("❌ Seleção inválida")
			}
			name = projects[idx-1].Name
		}
		runSwitchProject(name)
	},
}

func init() {
	projectCmd.AddCommand(projectSwitchCmd)
}

func runSwitchProject(name string) {
	// 1. Caso especial: home
	if name == "home" {
		core.SetContext("home")
		fmt.Println("✅ Contexto alterado para: home")
		return
	}

	// 2. Validação de nome
	if name != "a-ponte" {
		if err := validator.ValidateProjectName(name); err != nil {
			log.Fatalf("❌ Erro de validação: %v", err)
		}
	}

	// 3. Verifica no DynamoDB
	project, err := core.GetProject(name)
	if err != nil || project == nil {
		log.Fatalf("❌ Projeto não encontrado no registro: %s", name)
	}

	// 4. Hidrata arquivos locais e muda contexto (Reusa função do create)
	core.HydrateLocalFiles(project)

	// 5. Persiste o contexto e notifica
	core.SetContext(name)
	fmt.Printf("📍 Contexto alterado para: %s\n", name)
}
