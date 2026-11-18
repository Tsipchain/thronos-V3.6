# Thronos Basketball Market — Product & Technical Blueprint

Status: Phase 0 / Product bootstrap
Initial markets: Greek Basket League + EuroLeague
Working product name: **Thronos Basketball Market**
Suggested public brand alternatives: **ThronosHoops**, **HoopsMarket**, **BasketValue**
Target domain: `basketball.thronoschain.org` or standalone branded domain

## 1. Product thesis

Build the basketball-market equivalent of a football transfer intelligence portal, designed first for Greece and EuroLeague.

The service must not be a rumours-only publication. Its core product is a structured, searchable, provenance-aware market database for:
- players
- clubs
- agents / agencies
- contracts
- transfers
- free agents
- roster status
- injuries / availability where licensing permits
- statistics
- market-value estimates
- scouting notes
- verified professional claims

The differentiated Thronos layer is **proof and provenance**:
- every important professional declaration can be hashed
- verified agent / agency identities can be bound through VerifyID
- material profile changes can be anchored to ThronosChain
- source/evidence history is preserved
- disputed claims remain auditable

## 2. Initial customer groups

### Public users
- fans
- journalists
- basketball communities
- fantasy / analytics users

### Professional users
- licensed basketball agents
- agencies
- clubs
- scouts
- coaches
- journalists / media desks
- sponsors

First paid wedge: **Greek basketball agents and agencies**, then EuroLeague-facing agencies.

## 3. Core public pages

### Player profile
- full name
- photo
- nationality
- date of birth / age
- height
- position
- current club
- previous clubs
- current contract status
- contract expiry, when verified/public
- represented by / agency
- career stats
- transfer history
- injury / inactive status where lawfully sourced
- estimated market value range
- valuation confidence
- latest verified update
- source provenance
- verified badge
- Thronos proof ID for anchored profile snapshots

### Club profile
- league
- roster
- coach
- arrivals
- departures
- expiring contracts
- loan / temporary movement where applicable
- average age
- nationality breakdown
- agency concentration
- estimated roster value

### Agent / agency profile
- VerifyID-backed professional verification
- players represented
- leagues covered
- public contact channels
- agency page
- verified representation claims
- historical roster of clients
- subscription / professional dashboard

### Transfers
Filters:
- date
- league
- club
- nationality
- position
- agent / agency
- confirmed / reported / disputed
- free-agent signing / release / extension

### Free agents
- current availability
- last club
- position
- age
- represented by
- last verified date

## 4. Data trust model

Every field should have:
- value
- source_type
- source_url or internal evidence reference
- source_date
- confidence
- verified_by
- verified_at
- public/private visibility
- optional Thronos anchor txid/hash

Evidence states:
- OFFICIAL
- VERIFIED_PROFESSIONAL
- MULTI_SOURCE_CONFIRMED
- REPORTED
- DISPUTED
- EXPIRED

Never silently overwrite historical data. Important state changes are versioned.

## 5. Market valuation

Do not present a single unexplained number as fact.

Store:
- low_estimate
- central_estimate
- high_estimate
- currency
- model_version
- confidence_score
- methodology_summary
- last_calculated_at

Possible inputs:
- age
- current competition strength
- minutes / usage
- efficiency
- injury availability
- role
- contract duration
- nationality / passport constraints
- recent transfer demand
- EuroLeague / domestic performance
- comparable players
- verified salary / contract information when legally usable

The UI can show:
**Estimated Market Range: €X–€Y**
with a confidence indicator and methodology link.

## 6. Professional subscription model

### Free
- public profiles
- basic transfers
- limited search
- ads

### Agent Starter — suggested €29–49/month
- verified professional profile
- claim / update represented players
- upload player dossier
- public contact card
- reduced ads

### Agent Pro — suggested €99–149/month
- advanced player analytics
- comparison tools
- free-agent visibility controls
- player availability alerts
- private notes
- export PDF dossier
- higher search limits
- verified representation badge

### Agency / Club — suggested €299–599+/month
- multi-seat
- private scouting lists
- watchlists
- roster-gap analysis
- agent/player search
- expiring contract intelligence
- API / CSV exports
- priority verification
- white-label reports

Pricing is a commercial hypothesis and must be validated with 5–10 Greek agents before launch.

## 7. Advertising

Public traffic can monetize through:
- display ads
- native sponsor placements
- sponsored team/league pages
- equipment brands
- sports medicine
- training academies
- betting only if legally/commercially acceptable and separately reviewed
- ticketing / travel / merchandise

Professional subscribed pages should remain low-ad or ad-free.

## 8. Thronos integrations

### VerifyID
Use `thronos-verifyid` for:
- agent identity verification
- agency organization verification
- club staff verification
- verified profile ownership

### Wallet V1 auth
Professional users can later bind:
- normal account
- Wallet V1 identity
- signed professional actions

Suggested action scopes:
- `basketball_profile_claim`
- `basketball_representation_attest`
- `basketball_transfer_submit`
- `basketball_profile_update`
- `basketball_dossier_sign`

### Chain anchors
Anchor hashes only, not personal/private documents.

Suggested transaction/evidence types:
- `BASKETBALL_PLAYER_SNAPSHOT_V1`
- `BASKETBALL_AGENT_ATTEST_V1`
- `BASKETBALL_TRANSFER_PROOF_V1`
- `BASKETBALL_DOSSIER_PROOF_V1`

### Payment Gateway
Use Thronos Payment Gateway / Stripe for:
- subscriptions
- agency seats
- premium reports
- promoted professional listings

## 9. Proposed architecture

### New independent service
Recommended repo:
`Tsipchain/thronos-basketball-market`

Runtime:
- Backend: FastAPI
- Frontend: Next.js / React
- DB: PostgreSQL
- Cache/queues: Redis
- Search: PostgreSQL FTS initially; OpenSearch later if needed
- Object storage: S3-compatible for licensed media and dossiers
- Deployment: Railway
- CDN/frontend: Vercel or Railway
- Auth: email/OIDC + optional Wallet V1 binding
- Billing: Thronos Gateway / Stripe
- Identity: VerifyID

Do not put the operational basketball database inside the main chain ledger.

ThronosChain stores proofs, hashes, attestations and selected events only.

## 10. Initial data model

Core tables:
- users
- organizations
- professional_profiles
- agents
- agencies
- players
- clubs
- competitions
- seasons
- rosters
- contracts
- transfers
- player_stats
- injuries
- representation_claims
- evidence_records
- profile_versions
- valuations
- valuation_inputs
- watchlists
- dossiers
- subscriptions
- invoices
- ads
- sponsors
- audit_events
- chain_anchors

Important constraints:
- player canonical identity must not depend on name alone
- representation claims require effective dates
- source evidence must survive edits
- contract values can have visibility rules
- GDPR deletion/anonymization policy must be explicit

## 11. API v1

Public:
- `GET /api/v1/players`
- `GET /api/v1/players/{id}`
- `GET /api/v1/clubs`
- `GET /api/v1/clubs/{id}`
- `GET /api/v1/transfers`
- `GET /api/v1/free-agents`
- `GET /api/v1/agents`
- `GET /api/v1/agencies`
- `GET /api/v1/valuations/{player_id}`

Professional:
- `POST /api/v1/pro/players/{id}/claim`
- `POST /api/v1/pro/representation`
- `POST /api/v1/pro/transfer-submissions`
- `POST /api/v1/pro/dossiers`
- `POST /api/v1/pro/watchlists`
- `GET /api/v1/pro/alerts`

Verification:
- `POST /api/v1/evidence`
- `POST /api/v1/evidence/{id}/verify`
- `POST /api/v1/anchors`
- `GET /api/v1/anchors/{id}`

Billing:
- `POST /api/v1/billing/checkout`
- `POST /api/v1/billing/webhook`
- `GET /api/v1/billing/subscription`

## 12. MVP scope

Phase 1 should cover:
- Greek Basket League
- EuroLeague
- current clubs
- current rosters
- player profile pages
- club profile pages
- transfers
- agents/agencies
- basic search
- verified evidence model
- agent signup
- VerifyID integration
- subscription skeleton
- admin moderation console
- blockchain anchoring for verified representation and transfer records

Do not delay MVP for:
- full AI valuation engine
- every historical season
- every global league
- mobile app
- NFT features

## 13. Data acquisition rules

We must not assume that data visible on another site may be copied wholesale.

Use, in order of preference:
1. official league / club / federation publications
2. licensed data providers / APIs
3. direct agent/agency submissions
4. official social announcements
5. editorial research with evidence records
6. user reports queued for moderation

Never build the business on scraping another commercial database without reviewing its terms and database rights.

## 14. Competitive positioning

The target statement:

> The trusted basketball market graph for Europe — players, clubs, agents, contracts and verified moves, with evidence provenance.

Not merely:
> another basketball news site.

## 15. Go-to-market Greece

Pilot with a small circle of Greek agents.

Offer founding-agent benefits:
- permanent early-adopter badge
- free verification
- 3–6 month complimentary Pro period
- priority player-profile claiming
- agency landing page
- direct feedback channel

In exchange:
- validate representation data
- validate pricing
- provide workflow feedback
- introduce the platform to clubs/scouts

## 16. KPIs

Before expansion, track:
- verified player profiles
- verified agent profiles
- monthly active professional users
- active paid agents
- claimed players
- verified transfers
- profile correction turnaround time
- search-to-contact conversions
- subscription conversion rate
- monthly recurring revenue
- public organic search traffic
- sponsor/ad revenue

## 17. Phase roadmap

### Phase 0
- product specification
- naming/domain
- data rights review
- 5–10 agent interviews
- clickable UI prototype

### Phase 1
- Greek Basket League + EuroLeague MVP
- players/clubs/transfers/agents
- pro accounts
- verification
- subscriptions

### Phase 2
- EuroCup / Basketball Champions League
- alerts/watchlists
- advanced scouting
- valuation v1
- agency analytics

### Phase 3
- Europe-wide expansion
- club/scout SaaS
- data API
- multilingual
- sponsor marketplace

### Phase 4
- NBA Europe / wider global market if commercially justified

## 18. Immediate engineering next step

Create standalone repo `Tsipchain/thronos-basketball-market` and implement:
1. FastAPI skeleton
2. PostgreSQL schema
3. Next.js frontend
4. seed dataset for Greek Basket League + EuroLeague
5. agent verification flow
6. evidence/provenance system
7. subscription checkout
8. Thronos anchor adapter
9. admin moderation panel
10. CI/tests
