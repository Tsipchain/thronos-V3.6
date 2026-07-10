# THRONOS Real Estate Landing Page

Professional landing page and investor onboarding portal for THRONOS blockchain-verified real estate platform.

## 🎯 Features

- **Landing Page**: Optimized for investor acquisition
- **Three-Pillar Marketing**: VerifyID, Legal Substance, Property Portfolio
- **Interactive Calculator**: Real-time ROI calculation
- **Responsive Design**: Mobile-first, production-ready
- **Web3 Ready**: Integration with wallet connections and smart contracts
- **SEO Optimized**: Server-side rendering with Next.js

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Open browser
http://localhost:3000
```

## 📁 Project Structure

```
src/
├── app/
│   ├── layout.tsx           # Root layout
│   ├── page.tsx            # Home page
│   ├── globals.css         # Global styles
│   └── providers.tsx       # Client-side providers
├── components/
│   ├── Navigation.tsx      # Top navigation bar
│   ├── Hero.tsx           # Hero section
│   ├── ThreePillars.tsx   # Three-pillar ecosystem
│   ├── PropertyShowcase.tsx # Featured properties
│   ├── InvestorCalculator.tsx # ROI calculator
│   ├── Testimonials.tsx    # Investor testimonials
│   ├── CTA.tsx            # Call-to-action
│   └── Footer.tsx         # Footer
└── types/
    └── index.ts           # TypeScript types
```

## 🔧 Environment Variables

```
NEXT_PUBLIC_API_URL=http://localhost:3001
NEXT_PUBLIC_THRONOSCHAIN_RPC=http://localhost:8545
```

## 📊 Key Sections

### 1. Hero Section
- Headline: "The Future of Real Estate. Managed on the Blockchain."
- Subheadline: Investment overview
- CTA Buttons: "Explore Portfolio" + "Start Investor Onboarding"

### 2. Three-Pillar Ecosystem
- Pillar 1: VerifyID (5-min KYC/AML)
- Pillar 2: Corporate Substance (EU legal footprint)
- Pillar 3: Property Portfolio (200+ verified properties)

### 3. Interactive Calculator
- Drag to set investment amount (€10K - €1M)
- Real-time ROI calculation (6.5% baseline)
- Monthly yield display

### 4. Property Showcase
- Featured properties with yield and price
- Direct property cards with details
- "View Details" button for full listing

### 5. Testimonials
- 5-star reviews from real investors
- First name + country
- Real earnings examples

## 🎨 Design System

- **Primary Color**: #003366 (Navy Blue)
- **Accent Color**: #FFD700 (Gold)
- **Typography**: System UI, responsive scales
- **Spacing**: Tailwind CSS default scale

## 📱 Responsive Breakpoints

- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

## 🔗 Integration Points

### API Endpoints (Backend)
- `GET /api/properties` - List all properties
- `POST /api/verify/initiate` - Start KYC
- `POST /api/invest` - Create investment
- `GET /api/investor/:id` - Get investor portfolio

### Blockchain
- Smart contract calls for investment confirmation
- Wallet connection (MetaMask, WalletConnect)
- Thronoschain RPC integration

## 🚀 Deployment

```bash
# Build for production
npm run build

# Start production server
npm start
```

### Hosting Options
- Vercel (recommended for Next.js)
- AWS Amplify
- Azure App Service
- Self-hosted Docker

## 📝 To-Do

- [ ] Wire up API endpoints
- [ ] Implement wallet connection
- [ ] Add property image gallery
- [ ] Create investor dashboard
- [ ] Set up email notifications
- [ ] Add chatbot for support
- [ ] Implement analytics tracking

## 📞 Support

For issues or questions, contact the development team.

## 📄 License

Proprietary - THRONOS IKE
