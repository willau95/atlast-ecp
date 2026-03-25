# ECP Service Discovery

## `.well-known/ecp.json`

Any ECP-compatible server exposes a discovery endpoint at:

```
GET /.well-known/ecp.json
```

### Response

```json
{
  "protocol": "ecp",
  "version": "1.0",
  "server": "atlast-ecp",
  "server_version": "1.0.0",
  "endpoints": {
    "stats": "/v1/stats",
    "verify_merkle": "/v1/verify/merkle",
    "verify_attestation": "/v1/verify/{uid}",
    "attestations": "/v1/attestations"
  },
  "eas": {
    "chain": "sepolia",
    "chain_id": 84532,
    "schema_uid": "0xa67da7e880b3fe643f0e12b754c6048fc0a0bad0ed9a932ac85a5ebf6bd9326e"
  }
}
```

### Usage

Clients can discover ECP capabilities by fetching this endpoint:

```bash
curl https://api.weba0.com/.well-known/ecp.json
```

This follows the [RFC 8615](https://tools.ietf.org/html/rfc8615) `.well-known` URI convention.
