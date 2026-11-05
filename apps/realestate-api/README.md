# THRONOS Real Estate API

Backend API for THRONOS blockchain-verified real estate platform. Handles investor onboarding, property management, smart contract interactions, and KYC/AML verification.

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Set up environment variables
cp .env.example .env

# Run migrations (Prisma)
npm run migrate

# Start development server
npm run dev

# Start production server
npm run build && npm start
```

## 📋 API Endpoints

### Investors
- `GET /api/investors/:id` - Get investor profile
- `POST /api/investors` - Create new investor
- `PUT /api/investors/:id` - Update investor profile
- `GET /api/investors/:id/portfolio` - Get investor's properties

### Properties
- `GET /api/properties` - List all properties (with filters)
- `GET /api/properties/:id` - Get property details
- `POST /api/properties/:id/invest` - Invest in property
- `GET /api/properties/:id/analytics` - Get property analytics

### KYC/AML Verification
- `POST /api/verify/initiate` - Start verification process
- `GET /api/verify/:verificationId` - Get verification status
- `POST /api/verify/webhook` - Webhook for KYC service callbacks
- `POST /api/verify/:verificationId/reject` - Reject verification
- `GET /api/verify/wallet/:walletAddress` - Check wallet verification status

### Smart Contracts
- `POST /api/smartcontracts/deploy-property` - Deploy property smart contract
- `POST /api/smartcontracts/:contractAddress/mint-tokens` - Mint property tokens
- `GET /api/smartcontracts/:contractAddress/balance/:walletAddress` - Get token balance
- `POST /api/smartcontracts/:contractAddress/distribute-yield` - Distribute monthly yields
- `GET /api/smartcontracts/:contractAddress/history` - Get transaction history
- `POST /api/smartcontracts/encode-function-call` - Encode function call for signing

## 🔧 Environment Variables

See `.env.example` for all required environment variables.

### Critical Variables
- `DATABASE_URL` - PostgreSQL connection string
- `THRONOSCHAIN_RPC` - Thronoschain RPC endpoint
- `THRONOSCHAIN_PRIVATE_KEY` - Private key for contract deployment
- `KYC_PROVIDER` - KYC/AML service (stripe, idology, jumio)

## 📦 Architecture

```
src/
├── server.ts              # Express app & server setup
├── routes/                # API endpoint definitions
│   ├── investor.ts
│   ├── property.ts
│   ├── verify.ts
│   └── smartContract.ts
├── controllers/           # Business logic
├── middleware/            # Auth, validation, errors
├── models/                # Data models (Prisma)
└── lib/                   # Utilities & helpers
```

## 🔐 Security Features

- **CORS**: Restricted to frontend URL
- **Helmet**: HTTP security headers
- **Rate Limiting**: 100 requests per 15 minutes per IP
- **Input Validation**: Joi schemas for all endpoints
- **JWT Auth**: Token-based authentication
- **HTTPS**: All API calls should use HTTPS in production

## 🗄️ Database (Prisma)

```prisma
model Investor {
  id String @id @default(cuid())
  email String @unique
  walletAddress String @unique
  kycStatus KycStatus
  properties Property[]
  investments Investment[]
  createdAt DateTime @default(now())
}

model Property {
  id String @id @default(cuid())
  name String
  location String
  price Float
  totalShares Int
  monthlyRent Float
  contractAddress String @unique
  investors Investor[]
  createdAt DateTime @default(now())
}
```

## 🧪 Testing

```bash
# Run tests
npm test

# Test with coverage
npm run test:coverage
```

## 📊 Monitoring & Logging

- Winston logger for structured logging
- Morgan for HTTP request logging
- ELK stack ready (Elasticsearch, Logstash, Kibana)

## 🌐 Blockchain Integration

### Supported Networks
- Thronoschain (mainnet & testnet)
- Ethereum mainnet (for institutional transfers)

### Smart Contract Interactions
- Deploy property contracts (ERC721/ERC1155)
- Mint fractional shares
- Distribute yields via smart contracts
- Query blockchain state

## 📝 API Documentation

Interactive API docs available at:
- Swagger UI: `http://localhost:3001/api-docs`
- OpenAPI spec: `http://localhost:3001/api/openapi.json`

## 🚀 Deployment

### Docker
```bash
docker build -t thronos-realestate-api .
docker run -p 3001:3001 --env-file .env thronos-realestate-api
```

### Cloud Platforms
- **Railway**: `railway up`
- **Heroku**: `git push heroku main`
- **AWS ECS**: See cloudformation template
- **DigitalOcean App Platform**: Connect GitHub repo

## 🤝 Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Commit changes: `git commit -am 'Add feature'`
3. Push to branch: `git push origin feature/my-feature`
4. Open Pull Request

## 📞 Support

For issues, questions, or contributions, contact the development team.

## 📄 License

Proprietary - THRONOS IKE
