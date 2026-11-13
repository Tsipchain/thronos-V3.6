/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    remotePatterns: [
      { hostname: 'images.unsplash.com' },
      { hostname: '*.cloudinary.com' },
      { hostname: '*.thronos.io' }
    ]
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001',
    NEXT_PUBLIC_THRONOSCHAIN_RPC: process.env.NEXT_PUBLIC_THRONOSCHAIN_RPC || 'http://localhost:8545'
  },
  redirects: async () => {
    return [
      {
        source: '/portfolio',
        destination: '/properties',
        permanent: false
      }
    ];
  }
};

module.exports = nextConfig;
