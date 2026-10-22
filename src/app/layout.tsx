import type { Metadata } from 'next';
import { Suspense } from 'react';
import { Newsreader, Plus_Jakarta_Sans, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { ThemeProvider } from '@/components/ThemeProvider';
import { Navbar } from '@/components/Navbar';
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
        {/* Monetag Popunder / OnClick */}
        <script
          src="https://al5sm.com/tag.min.js"
          data-zone="12092686"
          async
          data-cfasync="false"
        />
        {/* Monetag In-Page Push (IPP) */}
        <script
          src="https://nap5k.com/tag.min.js"
          data-zone="12093786"
          async
          data-cfasync="false"
        />
        {/* Monetag Vignette */}
        <script
          src="https://n6wxm.com/vignette.min.js"
          data-zone="12093787"
          async
          data-cfasync="false"
        />
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
        </ThemeProvider>
      </body>
    </html>
  );
}
