const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: '/chat', destination: 'http://127.0.0.1:8000/chat' },
      { source: '/book-appointment', destination: 'http://127.0.0.1:8000/book-appointment' },
      { source: '/health', destination: 'http://127.0.0.1:8000/health' },
    ];
  },
};

export default nextConfig;
