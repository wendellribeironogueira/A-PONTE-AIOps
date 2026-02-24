package cmd

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"text/tabwriter"

	"aponte/cli/internal/core"
	"aponte/cli/internal/utils"

	"github.com/spf13/cobra"
)

var listOutputFormat string

var projectListCmd = &cobra.Command{
	Use:   "list",
	Short: "Lista todos os projetos registrados",
	Run: func(cmd *cobra.Command, args []string) {
		runListProjects()
	},
}

func init() {
	projectListCmd.Flags().StringVarP(&listOutputFormat, "output", "o", "table", "Formato de saída (table, json)")
	projectCmd.AddCommand(projectListCmd)
}

func runListProjects() {
	projects, err := core.ListProjects()
	if err != nil {
		log.Fatalf("❌ Erro ao listar projetos: %v", err)
	}

	// Estrutura para JSON e Table
	type ProjectItem struct {
		Name        string `json:"name"`
		Environment string `json:"environment"`
		Status      string `json:"status"`
		Local       bool   `json:"local"`
	}
	items := []ProjectItem{}

	for _, p := range projects {
		typeStr := "Workload"
		if p.IsProduction {
			typeStr = "🔒 Production"
		}

		// Verifica se existe localmente
		localPath := filepath.Join(utils.GetProjectRoot(), "projects", p.Name)
		_, err := os.Stat(localPath)
		isLocal := err == nil

		items = append(items, ProjectItem{
			Name:        p.Name,
			Environment: p.Environment,
			Status:      typeStr,
			Local:       isLocal,
		})
	}

	if listOutputFormat == "json" {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		if err := enc.Encode(items); err != nil {
			log.Fatalf("❌ Erro ao gerar JSON: %v", err)
		}
		return
	}

	// 3. Formatação de Saída (Tabular)
	w := tabwriter.NewWriter(os.Stdout, 0, 0, 3, ' ', 0)
	fmt.Fprintln(w, "ICON\tPROJETO\tAMBIENTE\tTIPO\tLOCAL")

	for _, p := range items {
		icon := "☁️"
		if p.Name == "a-ponte" || p.Name == "home" {
			icon = "🏠"
		}
		localIcon := "❌"
		if p.Local {
			localIcon = "✅"
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n", icon, p.Name, p.Environment, p.Status, localIcon)
	}
	w.Flush()
}
