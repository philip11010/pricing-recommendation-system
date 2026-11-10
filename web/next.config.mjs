/**
 * Next.js configuration.
 *
 * Deliberately small. The application talks to the pricing API directly from
 * the browser rather than through a rewrite, so that what the browser sends is
 * the same request the API documents, including the identity header. The API
 * address is configuration, read from NEXT_PUBLIC_API_URL.
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
