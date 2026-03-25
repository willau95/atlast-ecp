# ECP Troubleshooting (Quick Reference)

## .ecp/ missing → `atlast init`
## identity.json broken → delete it, run `atlast init` (new DID)
## chain broken → `python3 -c "from atlast_ecp.core import reset; reset()"`
## index.json broken → delete it, records are safe, will rebuild on next load
## upload failing → `atlast flush` (records safe locally, will retry)
## pip install fails → need Python 3.10+, try `pip install --user atlast-ecp`

Full guide: https://github.com/willau95/atlast-ecp/blob/main/SKILL.md
