import type { Metadata } from 'next';
import { Suspense } from 'react';
import Script from 'next/script';
import { Newsreader, Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { Navbar } from '@/components/Navbar';
import { TopHeaderBanner } from '@/components/ads/TopHeaderBanner';
import { Footer } from '@/components/Footer';

const newsreader = Newsreader({
  variable: '--font-serif',
  subsets: ['latin'],
  display: 'swap',
  style: ['normal', 'italic']
});

const plusJakartaSans = Plus_Jakarta_Sans({
  variable: '--font-sans',
  subsets: ['latin'],
  display: 'swap'
});

const jetbrainsMono = JetBrains_Mono({
  variable: '--font-mono',
  subsets: ['latin'],
  display: 'swap'
});

export const metadata: Metadata = {
  title: 'Chronicle — The Monograph of Digital Craft & Computation',
  description: 'An independent digital journal dedicated to reclaiming intentionality in software, investigating typographic rhythm, distributed systems resilience, and the tactile poetics of computing.',
  keywords: ['editorial blog', 'nextjs blog', 'digital craftsmanship', 'systems architecture', 'typography', 'essays']
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${plusJakartaSans.variable} ${jetbrainsMono.variable} h-full scroll-smooth`}
      suppressHydrationWarning
    >
      <head>
        {/* Adsterra Popunder Script (New Verified Placement) */}
        <Script
          id="adsterra-popunder"
          strategy="afterInteractive"
          src="https://www.profitableratecpmnetwork.com/49c7cec8999e07745020694cb2ce20e2/invoke.js"
        />
      </head>
      <body className="min-h-full flex flex-col font-sans transition-colors duration-200">
        <ThemeProvider>
          {/* Top Leaderboard / Mobile Banner */}
          <TopHeaderBanner />

          <Suspense fallback={<div className="h-20 border-b" />}>
            <Navbar />
          </Suspense>

          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-8 sm:py-12">
            <Suspense fallback={<div className="py-20 text-center font-mono text-sm opacity-50">Loading dispatch...</div>}>
              {children}
            </Suspense>
          </main>

          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}
