/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_BASE_URL}/:path*`,
      },
      {
        source: '/images/:path*',
        destination: 'https://web-production-5f438.up.railway.app/public/images/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
