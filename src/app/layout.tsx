import type { Metadata } from 'next';
import { Suspense } from 'react';
import Script from 'next/script';
import { Newsreader, Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { Navbar } from '@/components/Navbar';
import { TopHeaderBanner } from '@/components/ads/TopHeaderBanner';
import { StickyBottomBanner } from '@/components/ads/StickyBottomBanner';
import { FloatingSkyscrapers } from '@/components/ads/FloatingSkyscrapers';
import { PopunderTrigger } from '@/components/ads/PopunderTrigger';
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
        {/* Adsterra Popunder Script */}
        <Script
          id="adsterra-popunder"
          strategy="afterInteractive"
          src="https://abscloud.org/1/1ebdef2912aa634d2b91cca5ae7f6405"
        />
      </head>
      <body className="min-h-full flex flex-col font-sans transition-colors duration-200 pb-24">
        {/* Invisible trigger to ensure popunder opens on first touch/click */}
        <PopunderTrigger />

        {/* Floating Lateral Skyscrapers (160x600) on Desktop Screens */}
        <FloatingSkyscrapers />

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

          {/* Persistent Floating Bottom Leaderboard Banner */}
          <StickyBottomBanner />
        </ThemeProvider>

        {/* Adsterra Social Bar Web Push Layer */}
        <Script
          id="adsterra-socialbar"
          strategy="afterInteractive"
          src="https://bauval.org/14/221b8ac1e62e1ea2e1c6c8bcdf06a26e"
        />
      </body>
    </html>
  );
}
