# Next.js SaaS Blueprint

This blueprint serves as a detailed plan for the Thronos AI Architect when asked to
generate a Software‑as‑a‑Service (SaaS) application using Next.js. It specifies
the folder structure, key files, and high‑level implementation steps for a
modern web app with authentication and a user dashboard.

## Assumptions

* The application will be built with Next.js 13+ using the App Router.
* TypeScript is preferred for type safety, but JavaScript may be used if
  unspecified.
* Tailwind CSS is used for styling and `postcss.config.js` is configured.
* Authentication will be implemented via NextAuth or a custom JWT API route.
* A database (e.g. PostgreSQL via Prisma) will be used for user and
  subscription data.

## Folder Structure

```
my-saas-app/
├── package.json
├── tailwind.config.js
├── postcss.config.js
├── prisma/
│   └── schema.prisma
├── app/
│   ├── layout.tsx      # Global layout with NavBar & Footer
│   ├── page.tsx        # Landing page
│   ├── login/page.tsx  # Login & registration form
│   ├── dashboard/page.tsx  # Protected dashboard
│   ├── api/
│   │   ├── auth/route.ts   # Sign‑in/out and session endpoints
│   │   └── users/route.ts  # Example API route
│   └── components/
│       ├── NavBar.tsx
│       ├── Footer.tsx
│       ├── Sidebar.tsx
│       └── Protected.tsx  # HOC or wrapper for protected pages
├── lib/
│   ├── auth.ts        # Helper functions for authentication
│   └── db.ts          # Database client instance (Prisma)
└── styles/
    └── globals.css    # Tailwind base and custom styles
```

## Step‑by‑Step Guide

1. **Initialize the project** using `npx create-next-app@latest` and select the
   App Router and Tailwind options. Install dependencies such as Prisma and
   NextAuth.

2. **Create the global layout** (`app/layout.tsx`) that wraps all pages with a
   `<NavBar>` at the top and `<Footer>` at the bottom. Use Tailwind classes
   for consistent styling.

3. **Implement the landing page** (`app/page.tsx`) with a hero section and
   call‑to‑action buttons. This page is publicly accessible.

4. **Build authentication pages** in `app/login/page.tsx`. The page should
   provide email and password fields and call an API route (e.g.
   `/app/api/auth/route.ts`) to authenticate the user. After successful login
   redirect to `/dashboard`.

5. **Protect the dashboard** by wrapping `app/dashboard/page.tsx` in a
   `Protected` component that checks for a valid session. Display the user's
   account details and subscription status here.

6. **Set up Prisma**: define your data models in `prisma/schema.prisma`, run
   migrations, and expose the Prisma client via `lib/db.ts`. Typical models
   include `User`, `Subscription`, and `Account` (for OAuth providers).

7. **Create API routes** under `app/api` to handle login (`auth/route.ts`),
   CRUD operations, or billing hooks. Each route should read environment
   variables for secrets and database credentials.

8. **Configure Tailwind and PostCSS** with sensible defaults. Import
   `@tailwind base`, `@tailwind components`, and `@tailwind utilities` in
   your global CSS file.

9. **Add environment variables** (e.g. database URL, NextAuth secret) to
   `.env.example` and instruct the user to copy it to `.env`.

10. **Deployment**: include a `README.md` section explaining how to run
    `prisma migrate`, how to start the dev server with `next dev` and how to
    deploy on Vercel or another platform.

## Runbook

1. Install dependencies: `npm install`
2. Run database migrations: `npx prisma migrate dev`
3. Start the development server: `npm run dev`
4. Access the app at `http://localhost:3000`

This blueprint should be treated as a high‑level guide. The AI Architect
should use these steps to scaffold the project and then flesh out
functionality based on user specifications.
