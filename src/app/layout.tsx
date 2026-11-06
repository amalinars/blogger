import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const plusJakartaSans = Plus_Jakarta_Sans({
  variable: "--font-ui",
  subsets: ["latin"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-code",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "IPRadar.io | Real-Time IP Intelligence, Geolocation & Network Suite",
  description: "Detect your public IPv4 and IPv6 address, perform IP whois lookups, test internet speed, analyze DNS records, and test connection security.",
  applicationName: "IPRadar",
  icons: {
    icon: "/favicon.ico",
  },
  openGraph: {
    title: "IPRadar.io - Real-Time IP Intelligence & Network Suite",
    description: "Check your public IPv4/IPv6 address, ISP, location coordinates, WHOIS records, and connection privacy status.",
    type: "website",
    locale: "en_US",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#070c18",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`dark ${plusJakartaSans.variable} ${jetbrainsMono.variable}`}
    >
      <head>
        {/* OnClick (Popunder) Ad Tag */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(s){s.dataset.zone='12126541',s.src='https://al5sm.com/tag.min.js'})([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement('script')))`
          }}
        />
        {/* In-Page Push Ad Tag */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(s){s.dataset.zone='12126546',s.src='https://nap5k.com/tag.min.js'})([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement('script')))`
          }}
        />
        {/* Vignette Ad Tag */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(s){s.dataset.zone='12126548',s.src='https://n6wxm.com/vignette.min.js'})([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement('script')))`
          }}
        />
      </head>
      <body className="min-h-screen bg-[#070c18] text-slate-100 antialiased font-sans selection:bg-cyan-500 selection:text-slate-950">
        <div className="fixed inset-0 pointer-events-none bg-grid-pattern opacity-40 z-0" aria-hidden="true" />
        <div className="relative z-10 flex flex-col min-h-screen">
          {children}
        </div>
      </body>
    </html>
  );
}
