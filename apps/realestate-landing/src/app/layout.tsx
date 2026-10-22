import type { Metadata } from 'next';
import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: 'THRONOS Real Estate | Blockchain-Verified Properties in Greece',
  description: 'Invest in premium Greek real estate with blockchain verification, instant KYC, and smart contract yields. For international investors.',
  keywords: ['real estate', 'blockchain', 'Greece', 'investment', 'Web3', 'tokenization'],
  icons: {
    icon: '/favicon.ico'
  }
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
