import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#6C63FF',
        secondary: '#8F7CFF',
        surface: '#ffffffee',
        panel: '#f2f4fb',
        background: '#F8F9FC',
        text: '#1A1A1A',
      },
      boxShadow: {
        soft: '0 24px 60px rgba(108, 99, 255, 0.12)',
      },
      backdropBlur: {
        xs: '2px',
      },
      borderRadius: {
        xl: '1.5rem',
      },
    },
  },
  plugins: [],
};

export default config;
