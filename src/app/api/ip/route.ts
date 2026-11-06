import { NextRequest, NextResponse } from "next/server";
import { DEFAULT_IP_DATA, IpData } from "@/lib/types";

export const dynamic = "force-dynamic";

function isPrivateIp(ip: string): boolean {
  if (!ip) return true;
  return (
    ip === "127.0.0.1" ||
    ip === "::1" ||
    ip === "localhost" ||
    ip.startsWith("192.168.") ||
    ip.startsWith("10.") ||
    ip.startsWith("172.16.") ||
    ip.startsWith("172.17.") ||
    ip.startsWith("172.18.") ||
    ip.startsWith("172.19.") ||
    ip.startsWith("172.2") ||
    ip.startsWith("172.30.") ||
    ip.startsWith("172.31.")
  );
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get("query")?.trim();

    let targetUrl = "https://ipwho.is/";

    if (query) {
      const clean = query.replace(/^https?:\/\//i, "").split("/")[0].split(":")[0].trim();
      let resolvedIp = clean;

      // If domain name, resolve to IP
      if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(clean) && !clean.includes(":")) {
        try {
          const doh = await fetch(
            `https://dns.google/resolve?name=${encodeURIComponent(clean)}&type=A`,
            { headers: { Accept: "application/json" } }
          );
          if (doh.ok) {
            const dohData = await doh.json();
            const firstA = dohData.Answer?.find((a: { type: number; data: string }) => a.type === 1);
            if (firstA?.data) {
              resolvedIp = firstA.data;
            }
          }
        } catch {
          // fallback
        }
      }

      targetUrl = `https://ipwho.is/${encodeURIComponent(resolvedIp)}`;
    } else {
      // Check client headers
      const forwardedFor = request.headers.get("x-forwarded-for");
      const realIp = request.headers.get("x-real-ip");
      const cfIp = request.headers.get("cf-connecting-ip");

      const clientIp = cfIp || (forwardedFor ? forwardedFor.split(",")[0].trim() : realIp);

      if (clientIp && !isPrivateIp(clientIp)) {
        targetUrl = `https://ipwho.is/${encodeURIComponent(clientIp)}`;
      }
    }

    const res = await fetch(targetUrl, {
      headers: {
        Accept: "application/json",
        "User-Agent": "IPRadar-Next/1.0",
      },
      next: { revalidate: 60 },
    });

    if (!res.ok) {
      throw new Error(`Upstream returned ${res.status}`);
    }

    const data = await res.json();

    if (!data || data.success === false) {
      // Return default with error info if query was invalid
      return NextResponse.json({
        ...DEFAULT_IP_DATA,
        error: data.message || "Could not resolve IP",
        success: false,
      });
    }

    const formatted: IpData = {
      ip: data.ip || DEFAULT_IP_DATA.ip,
      type: data.type || (data.ip?.includes(":") ? "IPv6" : "IPv4"),
      success: true,
      continent: data.continent || "Asia",
      continent_code: data.continent_code || "AS",
      country: data.country || "Indonesia",
      country_code: data.country_code || "ID",
      region: data.region || "Jakarta Raya",
      region_code: data.region_code || "JW",
      city: data.city || "Jakarta",
      latitude: data.latitude ?? -6.2146,
      longitude: data.longitude ?? 106.8451,
      postal: data.postal || "12850",
      calling_code: data.calling_code || "62",
      capital: data.capital || "Jakarta",
      flag: {
        img: data.flag?.img || "https://cdn.ipwhois.io/flags/id.svg",
        emoji: data.flag?.emoji || "🇮🇩",
      },
      connection: {
        asn: data.connection?.asn || 4761,
        org: data.connection?.org || "IOH B2B",
        isp: data.connection?.isp || "IOH B2B",
        domain: data.connection?.domain || "ioh.co.id",
      },
      timezone: {
        id: data.timezone?.id || "Asia/Jakarta",
        abbr: data.timezone?.abbr || "WIB",
        utc: data.timezone?.utc || "+07:00",
      },
      ipv6: data.type === "IPv6" ? data.ip : null,
    };

    return NextResponse.json(formatted);
  } catch (err: unknown) {
    console.error("IP lookup error:", err);
    return NextResponse.json(DEFAULT_IP_DATA);
  }
}
