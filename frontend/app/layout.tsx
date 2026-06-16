import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'BOOKLY AI Appointment Agent',
  description: 'Chat-first salon booking assistant that recommends salons, answers FAQs, and books appointments conversationally.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-text antialiased">{children}</body>
    </html>
  );
}
