// atlast — ECP CLI for Go
//
// Usage:
//
//	atlast record --agent my-agent --action llm_call --input "hello" --output "world"
//	atlast log [--path records.jsonl]
//	atlast verify --path records.jsonl
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	ecp "github.com/willau95/atlast-ecp/sdk-go"
)

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "record":
		cmdRecord(os.Args[2:])
	case "log":
		cmdLog(os.Args[2:])
	case "verify":
		cmdVerify(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", os.Args[1])
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("Usage: atlast <command> [flags]")
	fmt.Println("")
	fmt.Println("Commands:")
	fmt.Println("  record   Create an ECP record")
	fmt.Println("  log      View stored records")
	fmt.Println("  verify   Verify record chain integrity")
}

func cmdRecord(args []string) {
	fs := flag.NewFlagSet("record", flag.ExitOnError)
	agent := fs.String("agent", "", "Agent identifier")
	action := fs.String("action", "llm_call", "Action type")
	input := fs.String("input", "", "Input text")
	output := fs.String("output", "", "Output text")
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	fs.Parse(args)

	if *agent == "" || *input == "" || *output == "" {
		fmt.Println("Required: --agent, --input, --output")
		os.Exit(1)
	}

	r := ecp.NewMinimalRecord(*agent, *action, *input, *output)
	if err := ecp.SaveRecord(*path, r); err != nil {
		fmt.Fprintf(os.Stderr, "Error saving record: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("✅ Recorded: %s (%s)\n", r.ID, r.Action)
}

func cmdLog(args []string) {
	fs := flag.NewFlagSet("log", flag.ExitOnError)
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	fs.Parse(args)

	records, err := ecp.LoadRecords(*path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading records: %v\n", err)
		os.Exit(1)
	}
	if len(records) == 0 {
		fmt.Println("No records found.")
		return
	}

	fmt.Printf("Found %d records:\n\n", len(records))
	for _, r := range records {
		fmt.Printf("  %s  %s  %s  %s\n", r.ID, r.Agent, r.Action, r.InHash[:30]+"...")
	}
}

func cmdVerify(args []string) {
	fs := flag.NewFlagSet("verify", flag.ExitOnError)
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	jsonOut := fs.Bool("json", false, "JSON output")
	fs.Parse(args)

	records, err := ecp.LoadRecords(*path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	var hashes []string
	for _, r := range records {
		hashes = append(hashes, ecp.ComputeChainHash(r))
	}
	root := ecp.BuildMerkleRoot(hashes)

	if *jsonOut {
		result := map[string]interface{}{
			"record_count": len(records),
			"merkle_root":  root,
			"chain_valid":  ecp.VerifyChain(records),
		}
		data, _ := json.MarshalIndent(result, "", "  ")
		fmt.Println(string(data))
	} else {
		fmt.Printf("Records: %d\n", len(records))
		fmt.Printf("Merkle Root: %s\n", root)
		fmt.Printf("Chain Valid: %v\n", ecp.VerifyChain(records))
	}
}
