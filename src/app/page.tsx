"use client";

import React, { useState, useEffect } from "react";
import { DEFAULT_IP_DATA, IpData } from "@/lib/types";
import { Navbar, ActiveTab } from "@/components/navbar";
import { TopAdBanner } from "@/components/top-ad-banner";
import { IpHero } from "@/components/ip-hero";
import { IpDetails } from "@/components/ip-details";
import { IpMap } from "@/components/ip-map";
import { SidebarAd } from "@/components/sidebar-ad";
import { VpnModal } from "@/components/vpn-modal";
import { NotificationBell } from "@/components/notification-bell";
import { BottomAdBar } from "@/components/bottom-ad-bar";
import { LeftSkyscraper, RightSkyscraper } from "@/components/skyscrapers";
import { Footer } from "@/components/footer";
import { SpeedTest } from "@/components/speed-test";
import { WhoisTool } from "@/components/whois-tool";
import { DnsTool } from "@/components/dns-tool";
import { IpLookupTool } from "@/components/ip-lookup-tool";
import { PrivacyTool } from "@/components/privacy-tool";

export default function HomePage() {
  const [ipData, setIpData] = useState<IpData>(DEFAULT_IP_DATA);
  const [loading, setLoading] = useState(false);
  const [vpnModalOpen, setVpnModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("my-ip");

  const fetchIpInfo = async (query?: string) => {
    setLoading(true);
    try {
      const url = query ? `/api/ip?query=${encodeURIComponent(query)}` : `/api/ip`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setIpData(data);
      }
    } catch (err) {
      console.error("Failed to fetch IP data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    async function loadInitial() {
      try {
        const res = await fetch("/api/ip");
        if (res.ok && active) {
          const data = await res.json();
          setIpData(data);
        }
      } catch (err) {
        console.error("Initial load error:", err);
      }
    }
    loadInitial();
    return () => {
      active = false;
    };
  }, []);

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    fetchIpInfo(query);
  };

  const handleRefresh = () => {
    fetchIpInfo(searchQuery || undefined);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#070c18] text-slate-100 selection:bg-cyan-500 selection:text-slate-950 font-sans">
      {/* Top Header & Ribbon Navigation */}
      <Navbar
        onSearch={handleSearch}
        isLoading={loading}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
      />

      {/* Top Sponsor Ad Banner */}
      <TopAdBanner />

      {/* Main Content Body */}
      <main className="flex-1 w-full max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6">
        <div className="flex justify-center items-start gap-6">
          {/* Left Skyscraper banner (2XL screens) */}
          <LeftSkyscraper />

          {/* Central Main Content */}
          <div className="w-full max-w-5xl space-y-6">
            {activeTab === "my-ip" && (
              <>
                {/* IP Hero (IPv4 & IPv6 Cards) */}
                <IpHero
                  data={ipData}
                  onRefresh={handleRefresh}
                  isRefreshing={loading}
                />

                {/* 3-Column Grid: Details, Map, Sidebar / Ad */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Column 1: IPv4 / IPv6 Details & VPN CTA */}
                  <div className="lg:col-span-5">
                    <IpDetails
                      data={ipData}
                      onOpenVpnModal={() => setVpnModalOpen(true)}
                    />
                  </div>

                  {/* Column 2: Approximate Location Map */}
                  <div className="lg:col-span-4">
                    <IpMap data={ipData} />
                  </div>

                  {/* Column 3: Partner & Tools Widget */}
                  <div className="lg:col-span-3">
                    <SidebarAd data={ipData} />
                  </div>
                </div>
              </>
            )}

            {activeTab === "lookup" && (
              <IpLookupTool initialIp={searchQuery || ipData.ip} />
            )}

            {activeTab === "whois" && (
              <WhoisTool initialIp={searchQuery || ipData.ip} />
            )}

            {activeTab === "speedtest" && (
              <SpeedTest data={ipData} />
            )}

            {activeTab === "dns" && (
              <DnsTool />
            )}

            {activeTab === "privacy" && (
              <PrivacyTool data={ipData} />
            )}
          </div>

          {/* Right Skyscraper banner (2XL screens) */}
          <RightSkyscraper />
        </div>
      </main>

      {/* Footer */}
      <Footer onSelectTab={setActiveTab} />

      {/* Floating Interactive Elements */}
      <NotificationBell data={ipData} />
      <BottomAdBar />
      <VpnModal
        isOpen={vpnModalOpen}
        onClose={() => setVpnModalOpen(false)}
        data={ipData}
      />
    </div>
  );
}
