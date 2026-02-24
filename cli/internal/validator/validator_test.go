package validator

import "testing"

func TestValidateProjectName(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		wantErr bool
	}{
		{"Valid simple", "myproject", false},
		{"Valid with hyphen", "my-project", false},
		{"Valid with number", "project1", false},
		{"Empty", "", true},
		{"Too long", "this-is-a-very-long-project-name-that-exceeds-forty-characters", true},
		{"Protected home", "home", true},
		{"Protected a-ponte", "a-ponte", true},
		{"Start with hyphen", "-project", true},
		{"End with hyphen", "project-", true},
		{"Uppercase", "Project", true},
		{"Special chars", "project!", true},
		{"Double hyphen allowed inside", "my--project", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := ValidateProjectName(tt.input); (err != nil) != tt.wantErr {
				t.Errorf("ValidateProjectName() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}
