# 🔐 THRONOS Real Estate - Blockchain Sealed Properties

**Digital Seals for Premium Properties. Immutable. Verified. Transparent.**

Complete platform for creating, managing, and verifying blockchain-sealed property records on Thronoschain.

---

## 📋 Project Structure

```
thronos-realestate/
├── seal-api/              # Node.js/Express API for seal operations
│   ├── src/
│   │   ├── routes/       # API endpoints
│   │   ├── blockchain/   # Smart contract interactions
│   │   └── lib/          # Utilities (logger, etc)
│   ├── package.json
│   └── README.md
│
├── smart-contracts/       # Solidity contracts
│   ├── contracts/
│   │   ├── PropertySeal.sol      # ERC721 seal NFTs
│   │   ├── SealRegistry.sol      # Central seal registry
│   │   └── MerkleVerifier.sol    # Proof verification
│   └── test/
│
├── seal-sdk/              # TypeScript SDK
│   ├── src/
│   │   ├── client.ts     # Main SDK client
│   │   ├── types.ts      # Type definitions
│   │   └── index.ts      # Exports
│   └── package.json
│
└── docs/
    ├── API.md            # API documentation
    ├── CONTRACTS.md      # Smart contract guide
    └── SDK.md            # SDK usage guide
```

---

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn
- Thronoschain RPC endpoint

### Installation

```bash
# Install all dependencies
npm install

# Or install individual workspaces
cd seal-api && npm install
cd seal-sdk && npm install
```

### Environment Setup

Create `.env` in `seal-api/`:

```env
NODE_ENV=development
PORT=3002
LOG_LEVEL=info

# Blockchain
THRONOSCHAIN_RPC=http://localhost:8545
THRONOSCHAIN_PRIVATE_KEY=0x...
PROPERTY_SEAL_CONTRACT=0x...
SEAL_REGISTRY_CONTRACT=0x...

# API
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

### Start Services

```bash
# Start Seal API
npm run dev:api

# API running on http://localhost:3002
# Health check: http://localhost:3002/health
```

---

## 📖 API Endpoints

### Seals
- `POST /api/seals/create` - Create new property seal
- `GET /api/seals/:sealId` - Get seal details
- `POST /api/seals/:sealId/verify` - Verify seal authenticity
- `GET /api/seals/property/:propertyId` - Get all seals for property
- `POST /api/seals/batch` - Create multiple seals

### Properties
- `GET /api/properties` - List all properties with seals
- `POST /api/properties/register` - Register property with seal
- `GET /api/properties/:propertyId` - Get property with seal history
- `POST /api/properties/:propertyId/update` - Update property and create seal

### Verification
- `POST /api/verify/merkle` - Verify merkle proof
- `POST /api/verify/signature` - Verify digital signature
- `GET /api/verify/public/:sealHash` - Public verification (no auth needed)

---

## 💻 SDK Usage

### Install SDK

```bash
npm install @thronos/seal-sdk
```

### Basic Usage

```typescript
import { SealClient } from '@thronos/seal-sdk';

const client = new SealClient({
  apiUrl: 'http://localhost:3002/api',
  rpcUrl: 'http://localhost:8545',
  contractAddress: '0x...'
});

// Create a seal
const seal = await client.createSeal({
  propertyId: 'prop_001',
  propertyName: 'Villa Petra',
  location: 'Ouranoupoli',
  ownerAddress: '0x...'
});

// Verify seal
const verification = await client.verifySeal(seal.id);
console.log('Seal is valid:', verification.isValid);

// Get property details
const property = await client.getProperty('prop_001');
console.log('Property seals:', property.seals);

// Public verification (anyone can call)
const publicVerif = await client.publicVerify(seal.sealHash);
```

---

## 🔗 Smart Contracts

### PropertySeal.sol
Main contract for creating and managing property seals as NFTs.

**Key Functions:**
- `createSeal()` - Mint new seal NFT
- `verifySeal()` - Check seal authenticity
- `updateSeal()` - Create new version with updated data
- `getSealHistory()` - Get all changes to seal

### SealRegistry.sol
Central registry for bulk verification.

**Key Functions:**
- `registerSeal()` - Register seal in registry
- `verifySealHash()` - Quick verification by hash
- `getPropertySeals()` - Get all seals for property

### Deploy Contracts

```bash
cd smart-contracts

# Compile
npx hardhat compile

# Deploy to testnet
npx hardhat run scripts/deploy.ts --network thronos-testnet

# Deploy to mainnet
npx hardhat run scripts/deploy.ts --network thronos-mainnet
```

---

## 📊 Data Flow

```
Property Registration
    ↓
┌─────────────────┐
│ Seal API        │  Creates digital fingerprint
└────────┬────────┘
         ↓
┌─────────────────┐
│ Smart Contracts │  Mints NFT + stores on blockchain
│ (PropertySeal)  │
└────────┬────────┘
         ↓
┌─────────────────┐
│ IPFS Storage    │  Stores documents & metadata
└────────┬────────┘
         ↓
┌─────────────────────────┐
│ Merkle Tree Proofs      │  Enables efficient verification
│ + Registry              │
└─────────────────────────┘
```

---

## 🔐 Security Features

✅ **Smart Contract Security**
- OpenZeppelin audited libraries
- ERC721 standard implementation
- Multi-sig wallet for treasury
- Timelock for critical operations

✅ **API Security**
- HTTPS enforced in production
- CORS whitelisting
- Rate limiting (100 req/15min per IP)
- Input validation with Joi
- JWT authentication ready

✅ **Data Privacy**
- Hash-based blockchain anchoring (no raw personal data)
- IPFS encryption for documents
- Consent-based verification
- GDPR compliant

---

## 📈 Performance

| Operation | Time | Cost (Thronoschain) |
|-----------|------|-------------------|
| Create Seal | < 5 sec | < $1 |
| Verify Seal | < 1 sec | < $0.10 |
| Merkle Proof | < 1 sec | < $0.05 |
| Batch (100) | < 30 sec | < $50 |

---

## 🧪 Testing

```bash
# Unit tests
npm run test:all

# API tests
cd seal-api && npm test

# Smart contract tests
cd smart-contracts && npm test
```

---

## 📡 Blockchain Integration

### Supported Networks
- **Thronoschain Testnet** (development)
- **Thronoschain Mainnet** (production)
- **Ethereum Mainnet** (bridge to institutional investors)

### Contract Addresses (Mainnet)
```
PropertySeal: 0x...
SealRegistry: 0x...
MerkleVerifier: 0x...
```

---

## 📚 Documentation

- [API Documentation](./docs/API.md)
- [Smart Contracts Guide](./docs/CONTRACTS.md)
- [SDK Usage Guide](./docs/SDK.md)
- [Deployment Guide](./docs/DEPLOYMENT.md)

---

## 🛠️ Development

### Local Setup with Docker

```bash
docker-compose up -d

# Services:
# - seal-api: http://localhost:3002
# - postgres: localhost:5432
# - redis: localhost:6379
# - ethereum: localhost:8545
```

### Contributing

1. Fork repository
2. Create feature branch: `git checkout -b feat/sealing-feature`
3. Commit changes: `git commit -am 'Add sealing feature'`
4. Push to branch: `git push origin feat/sealing-feature`
5. Submit Pull Request

---

## 📞 Support

- **Documentation**: See `/docs` folder
- **Issues**: GitHub Issues
- **Email**: support@thronos.io
- **Discord**: [THRONOS Community](https://discord.gg/thronos)

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🎯 Roadmap

- [x] PropertySeal.sol contract
- [x] Seal API core endpoints
- [x] TypeScript SDK
- [ ] Public verification dashboard
- [ ] Mobile app for seal verification
- [ ] AI-powered fraud detection
- [ ] Cross-chain bridging
- [ ] Institutional API tier

---

**Made with ❤️ by THRONOS Team**

*Transforming Real Estate through Blockchain Verification*
