import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Newsreader, Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { Navbar } from '@/components/Navbar';
import { Footer } from '@/components/Footer';
import { AAdsStickyUnits } from '@/components/ads/AAdsStickyUnits';

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
        {/* HilltopAds Verification */}
        <meta
          name="72c7af1256ac05236eaa49980a667d48e07b8033"
          content="72c7af1256ac05236eaa49980a667d48e07b8033"
        />
        {/* Referrer Policy for Maximum Ad Network Revenue (HilltopAds & A-Ads) */}
        <meta name="referrer" content="no-referrer-when-downgrade" />
      </head>
      <body className="min-h-full flex flex-col font-sans transition-colors duration-200">
        <ThemeProvider>
          <Suspense fallback={<div className="h-20 border-b" />}>
            <Navbar />
          </Suspense>

          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-8 py-8 sm:py-12">
            <Suspense fallback={<div className="py-20 text-center font-mono text-sm opacity-50">Loading dispatch...</div>}>
              {children}
            </Suspense>
          </main>

          <Footer />

          {/* A-Ads Multi-Unit Sticky Stream (Top, Left, Right, Bottom) */}
          <AAdsStickyUnits />
        </ThemeProvider>
      </body>
    </html>
  );
}
