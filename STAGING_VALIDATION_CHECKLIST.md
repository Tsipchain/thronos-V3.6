# PR #474 Staging Validation Checklist

## Test Credentials
- **STAGING_MASTER_URL**: (deployed by user)
- **STAGING_REPLICA_URL**: (deployed by user)

---

## Pre-Staging Verification ✅

### Grep Guards (Clean Checkout)
```bash
✅ PASS: No HmacSHA256 in production signing paths
✅ PASS: No publicKeyUncompressed in production signing files
✅ PASS: No uncompressed publicKey in signed envelopes
```

---

## Staging Master Endpoint Tests

### 1. Read Endpoints Should Return 200

**Dashboard Endpoint**
```bash
curl -X GET ${STAGING_MASTER_URL}/api/dashboard
# Expected: HTTP 200 OK
```

**Transaction Feed Endpoint**
```bash
curl -X GET ${STAGING_MASTER_URL}/api/tx_feed
# Expected: HTTP 200 OK
```

**Transfers Endpoint**
```bash
curl -X GET ${STAGING_MASTER_URL}/api/transfers
# Expected: HTTP 200 OK
```

---

### 2. Transaction Signing Validation

#### Test 2a: Unsigned Transaction Rejected
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_test_unsigned_001",
      "timestamp": 1710000000
    }
  }'
# Expected: HTTP 400 (missing signature)
```

#### Test 2b: Invalid Signature Rejected
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_test_invalid_sig_001",
      "timestamp": 1710000000,
      "signature": "0000000000000000000000000000000000000000000000000000000000000000",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 400 (invalid_signature)
```

#### Test 2c: Milliseconds Timestamp Rejected
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_test_ms_timestamp_001",
      "timestamp": 1710000000000,
      "signature": "304402203505194ba8f98847f7c4506004f107ee99b73c734af0175c9afb56841cc62a890220319211f1617059e5d6172ddbc374896239fb9a25debaa1324e064209c2d50a05",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 400 (timestamp_in_milliseconds or invalid_timestamp)
```

#### Test 2d: HMAC Signature Rejected
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_test_hmac_001",
      "timestamp": 1710000000,
      "signature": "12a1b2c3d4e5f6789a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 400 (invalid_signature)
```

#### Test 2e: Public Key/Address Mismatch Rejected
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "to": "THR0000000000000000000000000000000000000",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_test_mismatch_001",
      "timestamp": 1710000000,
      "signature": "304402203505194ba8f98847f7c4506004f107ee99b73c734af0175c9afb56841cc62a890220319211f1617059e5d6172ddbc374896239fb9a25debaa1324e064209c2d50a05",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 400 (address_mismatch or invalid_address)
```

#### Test 2f: Valid Golden Vector Transaction Accepted
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_golden_vector_001",
      "timestamp": 1710000000,
      "signature": "304402203505194ba8f98847f7c4506004f107ee99b73c734af0175c9afb56841cc62a890220319211f1617059e5d6172ddbc374896239fb9a25debaa1324e064209c2d50a05",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 200 OK (transaction accepted)
# Response should include: transaction ID, confirmation status, or similar
```

---

## Staging Replica Tests

### 1. Replica Rejects Write Operations
```bash
curl -X POST ${STAGING_REPLICA_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_test_replica_001",
      "timestamp": 1710000000,
      "signature": "304402203505194ba8f98847f7c4506004f107ee99b73c734af0175c9afb56841cc62a890220319211f1617059e5d6172ddbc374896239fb9a25debaa1324e064209c2d50a05",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 503 with error message containing "read_only_replica"
```

### 2. Replica Accepts Read Operations
```bash
curl -X GET ${STAGING_REPLICA_URL}/api/dashboard
# Expected: HTTP 200 OK

curl -X GET ${STAGING_REPLICA_URL}/api/tx_feed
# Expected: HTTP 200 OK

curl -X GET ${STAGING_REPLICA_URL}/api/transfers
# Expected: HTTP 200 OK
```

---

## Golden Vector Test Transaction

**Signed with real ECDSA/secp256k1**

```json
{
  "from": "THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5",
  "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
  "amount": 100,
  "token": "THR",
  "nonce": "tx_golden_vector_001",
  "timestamp": 1710000000,
  "signature": "304402203505194ba8f98847f7c4506004f107ee99b73c734af0175c9afb56841cc62a890220319211f1617059e5d6172ddbc374896239fb9a25debaa1324e064209c2d50a05",
  "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
}
```

**Properties:**
- Public Key: Compressed secp256k1 (66 hex chars, 02 prefix) ✅
- Signature: DER-encoded ECDSA ✅
- Timestamp: UNIX seconds (1710000000 = 2024-03-10 00:00:00 UTC) ✅
- Canonical: Sorted keys, compact JSON ✅

---

## Expected Results Summary

| Test | Master | Replica | Status |
|------|--------|---------|--------|
| `/api/dashboard` | 200 | 200 | ✅ |
| `/api/tx_feed` | 200 | 200 | ✅ |
| `/api/transfers` | 200 | 200 | ✅ |
| Unsigned TX | 400 | N/A | ✅ |
| Invalid Signature | 400 | N/A | ✅ |
| Milliseconds Timestamp | 400 | N/A | ✅ |
| HMAC Signature | 400 | N/A | ✅ |
| PublicKey/Address Mismatch | 400 | N/A | ✅ |
| Valid Golden Vector TX | 200 | N/A | ✅ |
| Write Operation | N/A | 503 | ✅ |
| Read Operations | N/A | 200 | ✅ |

---

## Validation Evidence

Once staging is deployed, run the above tests and paste:
1. Exact curl responses for each test
2. HTTP status codes
3. Error messages (if any)
4. Successful transaction responses

**Do NOT merge PR #474** until all staging tests pass with evidence pasted.
