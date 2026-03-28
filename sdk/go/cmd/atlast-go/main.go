// atlast-go — ECP CLI (Go SDK)
//
// Usage:
//
//	atlast-go record --agent my-agent --input "hello" --output "world"
//	atlast-go log
//	atlast-go push
//	atlast-go verify [--json]
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	ecp "github.com/willau95/atlast-ecp/sdk/go"
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
	case "push":
		cmdPush(os.Args[2:])
	case "verify":
		cmdVerify(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "Unknown command: %s\n", os.Args[1])
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("Usage: atlast-go <command> [flags]")
	fmt.Println()
	fmt.Println("Commands:")
	fmt.Println("  record   Create and save an ECP record")
	fmt.Println("  log      List recent records")
	fmt.Println("  push     Upload a batch to the ATLAST API")
	fmt.Println("  verify   Verify record chain integrity")
}

func cmdRecord(args []string) {
	fs := flag.NewFlagSet("record", flag.ExitOnError)
	agent := fs.String("agent", "", "Agent identifier (required)")
	action := fs.String("action", "llm_call", "Action type")
	input := fs.String("input", "", "Input text (required)")
	output := fs.String("output", "", "Output text (required)")
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	fs.Parse(args)

	if *agent == "" || *input == "" || *output == "" {
		fmt.Fprintln(os.Stderr, "Required flags: --agent, --input, --output")
		os.Exit(1)
	}

	r := ecp.NewMinimalRecord(*agent, *action, *input, *output)
	if err := ecp.SaveRecord(*path, r); err != nil {
		fmt.Fprintf(os.Stderr, "Error saving record: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Recorded: %s  action=%s  in=%s\n", r.ID, r.Action, r.InHash[:14]+"...")
}

func cmdLog(args []string) {
	fs := flag.NewFlagSet("log", flag.ExitOnError)
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	n := fs.Int("n", 20, "Number of recent records to show")
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

	// Show last n records
	start := len(records) - *n
	if start < 0 {
		start = 0
	}
	recent := records[start:]

	fmt.Printf("%d records (showing %d):\n\n", len(records), len(recent))
	for _, r := range recent {
		inHash := r.InHash
		if len(inHash) > 20 {
			inHash = inHash[:20] + "..."
		}
		fmt.Printf("  %-20s  %-16s  %-12s  %s\n", r.ID, r.Agent, r.Action, inHash)
	}
}

func cmdPush(args []string) {
	fs := flag.NewFlagSet("push", flag.ExitOnError)
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	apiURL := fs.String("api-url", "", "API URL (default: from config/env)")
	apiKey := fs.String("api-key", "", "API key (default: from config/env)")
	fs.Parse(args)

	// Priority: flag > env/config
	url := *apiURL
	if url == "" {
		url = ecp.GetAPIURL()
	}
	key := *apiKey
	if key == "" {
		key = ecp.GetAPIKey()
	}

	records, err := ecp.LoadRecords(*path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading records: %v\n", err)
		os.Exit(1)
	}
	if len(records) == 0 {
		fmt.Println("No records to push.")
		return
	}

	batch := ecp.BuildBatch(records)
	fmt.Printf("Pushing batch %s (%d records, root=%s...)\n",
		batch.ID, batch.RecordCount, batch.MerkleRoot[:20])

	// Load identity for agent_did and signing
	identity, err := ecp.GetOrCreateIdentity()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Identity error: %v\n", err)
		os.Exit(1)
	}
	sig := ecp.SignData(identity, batch.MerkleRoot)

	if err := ecp.UploadBatch(url, key, identity.DID, sig, batch); err != nil {
		fmt.Fprintf(os.Stderr, "Upload failed: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Batch uploaded successfully.")
}

func cmdVerify(args []string) {
	fs := flag.NewFlagSet("verify", flag.ExitOnError)
	path := fs.String("path", ecp.DefaultPath(), "Records file path")
	jsonOut := fs.Bool("json", false, "Output as JSON")
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
	chainValid := ecp.VerifyChain(records)

	if *jsonOut {
		result := map[string]interface{}{
			"record_count": len(records),
			"merkle_root":  root,
			"chain_valid":  chainValid,
		}
		data, _ := json.MarshalIndent(result, "", "  ")
		fmt.Println(string(data))
	} else {
		fmt.Printf("Records:     %d\n", len(records))
		fmt.Printf("Merkle Root: %s\n", root)
		fmt.Printf("Chain Valid: %v\n", chainValid)
	}
}
