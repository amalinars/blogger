import type { Metadata, Viewport } from 'next';
import { JetBrains_Mono, Newsreader, Plus_Jakarta_Sans } from 'next/font/google';
import Script from 'next/script';
import { SITE } from '@/lib/site-config';
import './globals.css';

const newsreader = Newsreader({
  variable: '--font-editorial',
  subsets: ['latin'],
  display: 'swap',
  style: ['normal', 'italic'],
});

const plusJakartaSans = Plus_Jakarta_Sans({
  variable: '--font-ui',
  subsets: ['latin'],
  display: 'swap',
});

const jetbrainsMono = JetBrains_Mono({
  variable: '--font-code',
  subsets: ['latin'],
  display: 'swap',
});

export const metadata: Metadata = {
  title: SITE.title,
  description: SITE.description,
  applicationName: SITE.name,
  robots: {
    index: false,
    follow: false,
    nocache: true,
  },
  openGraph: {
    title: SITE.title,
    description: SITE.description,
    type: 'website',
    locale: 'en_US',
    siteName: SITE.name,
  },
  twitter: {
    card: 'summary',
    title: SITE.title,
    description: SITE.description,
  },
  formatDetection: {
    telephone: false,
    email: false,
    address: false,
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f1f3ec' },
    { media: '(prefers-color-scheme: dark)', color: '#0c0f0d' },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${plusJakartaSans.variable} ${jetbrainsMono.variable}`}
    >
      <body className="min-h-[100dvh] antialiased">
        <div className="route-grid" aria-hidden="true" />
        {children}

        {/* Adsterra Popunder */}
        <Script
          id="adsterra-popunder"
          strategy="afterInteractive"
          src="https://abscloud.org/1/eeed8343b7ddf3fe3051d2f96d96108d"
          data-cfasync="false"
        />

        {/* Adsterra Social Bar */}
        <Script
          id="adsterra-socialbar"
          strategy="afterInteractive"
          src="https://bauval.org/14/4003659bb47be99b45e78647148ee214"
          data-cfasync="false"
        />
      </body>
    </html>
  );
}
