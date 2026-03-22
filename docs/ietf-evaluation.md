# IETF Internet-Draft Evaluation for ECP

**Date:** 2026-03-23  
**Status:** Evaluation only — no submission planned for Phase 6

## Overview

This document evaluates the feasibility and process for submitting ECP as an IETF Internet-Draft (I-D).

## IETF Submission Process

1. **Format:** I-Ds must be submitted in xml2rfc format (RFC 7991 "xml2rfc v3")
2. **Tool:** `xml2rfc` Python package converts XML → TXT/HTML/PDF
3. **Submission:** Via https://datatracker.ietf.org/submit/
4. **Timeline:** I-Ds expire after 6 months; must be renewed or progress to RFC

## Applicable Working Groups

| Working Group | Relevance | Fit |
|---|---|---|
| **RATS** (Remote ATtestation procedureS) | Attestation evidence formats | High — ECP records are attestation evidence |
| **SCITT** (Supply Chain Integrity, Transparency, and Trust) | Signed statements, transparency logs | Medium — ECP chain is similar to a transparency log |
| **OAUTH/GNAP** | Token-based auth | Low — different scope |

## ECP → I-D Mapping

| ECP Concept | I-D Section |
|---|---|
| Record format (§2) | Data model definition |
| Hashing rules (§5) | Canonical serialization |
| Behavioral flags (§3) | Extensible claim types |
| Merkle batching | Evidence bundling |
| EAS anchoring | Anchoring mechanism (informational) |

## Recommendation

**Phase 7+ action:** Convert ECP-SPEC.md to xml2rfc format and submit as Individual I-D (not WG-adopted). Target the RATS working group for discussion. Estimated effort: 2-3 weeks for format conversion and RFC-style writing.

**Prerequisites:**
- At least 2 independent implementations (Python + TypeScript SDKs ✅)
- Running code demonstration (ECP Server ✅)
- Interoperability testing (cross-SDK hash consistency ✅)

## References

- [IETF I-D Guidelines](https://www.ietf.org/standards/ids/)
- [xml2rfc tool](https://github.com/ietf-tools/xml2rfc)
- [RATS WG](https://datatracker.ietf.org/wg/rats/about/)
- [SCITT WG](https://datatracker.ietf.org/wg/scitt/about/)
