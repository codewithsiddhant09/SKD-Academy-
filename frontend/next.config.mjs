const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: '/chat', destination: 'http://127.0.0.1:5000/api/v1/chat' },
      { source: '/book-appointment', destination: 'http://127.0.0.1:5000/api/v1/book-appointment' },
      { source: '/health', destination: 'http://127.0.0.1:5000/api/v1/health' },
    ];
  },
};

export default nextConfig;
