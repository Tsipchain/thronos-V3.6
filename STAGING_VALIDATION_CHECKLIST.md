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

#### Test 2e: Public Key/Address Mismatch Rejected (Old Golden Vector)
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
# Expected: HTTP 400 (address_mismatch OR timestamp_expired)
# Reason 1: Address does NOT match publicKey (publicKey derives to THR751E76E8199196D454941C45D1B3A323F1433BD6)
# Reason 2: Timestamp 1710000000 is old (2024-03-10), fails ±5 min drift validation
```

#### Test 2f: Valid Fresh Signed Transaction Accepted
```bash
curl -X POST ${STAGING_MASTER_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR751E76E8199196D454941C45D1B3A323F1433BD6",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_staging_1779212171",
      "timestamp": 1779212171,
      "signature": "30440220018ad87c4581249ae5906ee26e0d996910461d8b7b56a9c798d09a752b99651202206769947d7a756b3a6d61bfa12dafd3fb9ad7fbd044c6c89e028f0cdccc5681fb",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 200 OK (transaction accepted)
# Response should include: transaction ID, confirmation status, or similar
# Verification:
# - Address THR751E76E8199196D454941C45D1B3A323F1433BD6 = RIPEMD160(SHA256(publicKey))
# - Timestamp 1779212171 is current UNIX seconds (within ±5 min drift)
# - Signature is DER-encoded ECDSA/secp256k1
# - Public Key is compressed (66 hex chars, 02 prefix)
```

---

## Staging Replica Tests

### 1. Replica Rejects Write Operations (Using Valid Fresh Signed TX)
```bash
curl -X POST ${STAGING_REPLICA_URL}/api/v1/tx/send \
  -H "Content-Type: application/json" \
  -d '{
    "tx": {
      "from": "THR751E76E8199196D454941C45D1B3A323F1433BD6",
      "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
      "amount": 100,
      "token": "THR",
      "nonce": "tx_staging_1779212171",
      "timestamp": 1779212171,
      "signature": "30440220018ad87c4581249ae5906ee26e0d996910461d8b7b56a9c798d09a752b99651202206769947d7a756b3a6d61bfa12dafd3fb9ad7fbd044c6c89e028f0cdccc5681fb",
      "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    }
  }'
# Expected: HTTP 503 with error message containing "read_only_replica"
# Note: Even though the transaction is valid, replica must reject ALL writes
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

## Fresh Signed Test Transaction (For Staging Validation)

**Signed with real ECDSA/secp256k1**

```json
{
  "from": "THR751E76E8199196D454941C45D1B3A323F1433BD6",
  "to": "THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF",
  "amount": 100,
  "token": "THR",
  "nonce": "tx_staging_1779212171",
  "timestamp": 1779212171,
  "signature": "30440220018ad87c4581249ae5906ee26e0d996910461d8b7b56a9c798d09a752b99651202206769947d7a756b3a6d61bfa12dafd3fb9ad7fbd044c6c89e028f0cdccc5681fb",
  "publicKey": "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
}
```

**Properties:**
- From Address: THR751E76E8199196D454941C45D1B3A323F1433BD6 (derived from publicKey via RIPEMD160(SHA256())) ✅
- Public Key: Compressed secp256k1 (66 hex chars, 02 prefix) ✅
- Signature: DER-encoded ECDSA ✅
- Timestamp: UNIX seconds (1779212171, current time within ±5 min drift) ✅
- Canonical: Sorted keys, compact JSON ✅

## Old Golden Vector (For Rejection Testing)

The old golden vector with timestamp 1710000000 (2024-03-10) will be rejected for TWO reasons:
1. **Address Mismatch**: from="THR7D865DCC21E8B5D5D8B5B5D5D5D5D5D5" does NOT match the public key (derives to THR751E76E8199196D454941C45D1B3A323F1433BD6)
2. **Expired Timestamp**: 1710000000 is old and fails the ±5 minute drift validation

Expected rejection: HTTP 400 (address_mismatch OR timestamp_expired or similar)

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
| Old Golden Vector (mismatch + expired) | 400 | N/A | ✅ |
| Valid Fresh Signed TX | 200 | N/A | ✅ |
| Write Operation on Replica | N/A | 503 | ✅ |
| Read Operations on Replica | N/A | 200 | ✅ |

---

## Validation Evidence

Once staging is deployed, run the above tests and paste:
1. Exact curl responses for each test
2. HTTP status codes
3. Error messages (if any)
4. Successful transaction responses

**Do NOT merge PR #474** until all staging tests pass with evidence pasted.
