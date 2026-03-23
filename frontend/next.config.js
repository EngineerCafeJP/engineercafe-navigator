/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      allowedOrigins: [
        "localhost:3000",
        "engineer-cafe-navigator.company-997.workers.dev",
      ],
    },
  },
  // WebSocket support for external integrations
  webpack: (config, { isServer }) => {
    // Enable file watching with polling for Docker on Windows (only when CHOKIDAR_USEPOLLING is set)
    if (process.env.CHOKIDAR_USEPOLLING === 'true') {
      config.watchOptions = {
        poll: 1000, // Check for changes every second
        aggregateTimeout: 300, // Delay rebuild after first change
      };
    }

    config.externals.push({
      "node:buffer": "commonjs buffer",
    });

    // Ignore markdown files in node_modules
    config.module.rules.push({
      test: /\.md$/,
      loader: "ignore-loader",
    });

    // Handle native modules
    config.module.rules.push({
      test: /\.node$/,
      loader: "node-loader",
    });

    // Additional fixes for libsql package
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
        crypto: false,
      };
    }

    // Externalize problematic modules for server-side
    if (isServer) {
      config.externals.push("libsql", "@libsql/client");
    }

    return config;
  },
  // Support for loading VRM models and assets
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "img-src 'self' data: blob: https:",
              "font-src 'self' data: https://fonts.gstatic.com",
              "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://*.run.app",
              "media-src 'self' blob: data:",
              "worker-src 'self' blob:",
              "frame-src 'self' blob: data:",
              "object-src 'none'",
              "base-uri 'self'",
            ].join("; "),
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Cross-Origin-Embedder-Policy",
            value: "unsafe-none",
          },
          {
            key: "Cross-Origin-Opener-Policy",
            value: "same-origin-allow-popups",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
