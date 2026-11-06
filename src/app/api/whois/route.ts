import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function isIpAddress(str: string): boolean {
  // IPv4 or IPv6
  return /^(\d{1,3}\.){3}\d{1,3}$/.test(str) || str.includes(":");
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get("query")?.trim();

    if (!query) {
      return NextResponse.json({ error: "Query parameter is required" }, { status: 400 });
    }

    const cleanQuery = query.replace(/^https?:\/\//i, "").split("/")[0].split(":")[0].trim();
    let targetIp = cleanQuery;
    let resolvedDomain = "";

    // If query is a domain, resolve to IPv4 first
    if (!isIpAddress(cleanQuery)) {
      resolvedDomain = cleanQuery;
      try {
        const doh = await fetch(
          `https://dns.google/resolve?name=${encodeURIComponent(cleanQuery)}&type=A`,
          { headers: { Accept: "application/json" } }
        );
        if (doh.ok) {
          const dohData = await doh.json();
          const firstA = dohData.Answer?.find((a: { type: number; data: string }) => a.type === 1);
          if (firstA?.data) {
            targetIp = firstA.data;
          }
        }
      } catch (e) {
        console.error("DoH resolve failed:", e);
      }
    }

    // Parallel fetch: RDAP + ipwho.is + PTR reverse DNS
    let inAddr = "";
    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(targetIp)) {
      inAddr = `${targetIp.split(".").reverse().join(".")}.in-addr.arpa`;
    }

    const [rdapPromise, ipwhoPromise, ptrPromise] = await Promise.allSettled([
      fetch(`https://rdap.arin.net/registry/ip/${encodeURIComponent(targetIp)}`, {
        headers: { Accept: "application/rdap+json", "User-Agent": "curl/7.81.0" },
        next: { revalidate: 300 },
      }).then((r) => (r.ok ? r.json() : null)),

      fetch(`https://ipwho.is/${encodeURIComponent(targetIp)}`, {
        headers: { Accept: "application/json" },
        next: { revalidate: 300 },
      }).then((r) => (r.ok ? r.json() : null)),

      inAddr
        ? fetch(`https://dns.google/resolve?name=${inAddr}&type=PTR`, {
            headers: { Accept: "application/json" },
          }).then((r) => (r.ok ? r.json() : null))
        : Promise.resolve(null),
    ]);

    const rdap = rdapPromise.status === "fulfilled" ? rdapPromise.value : null;
    const ipwho = ipwhoPromise.status === "fulfilled" ? ipwhoPromise.value : null;
    const ptr = ptrPromise.status === "fulfilled" ? ptrPromise.value : null;

    const hostname = ptr?.Answer?.[0]?.data?.replace(/\.$/, "") || ipwho?.connection?.domain || "";
    const netName = rdap?.name || ipwho?.connection?.org || "Allocated Network";
    const handle = rdap?.handle || `${targetIp}/32`;
    const startAddress = rdap?.startAddress || targetIp;
    const endAddress = rdap?.endAddress || targetIp;
    const cidr = rdap?.cidr0_cidrs?.[0]
      ? `${rdap.cidr0_cidrs[0].v4prefix || targetIp}/${rdap.cidr0_cidrs[0].length}`
      : `${startAddress} - ${endAddress}`;

    const asn = ipwho?.connection?.asn || 0;
    const org = ipwho?.connection?.org || rdap?.entities?.[0]?.handle || "Unknown Organization";
    const isp = ipwho?.connection?.isp || org;
    const country = ipwho?.country || "Global";
    const countryCode = ipwho?.country_code || "--";
    const city = ipwho?.city || "Unknown";
    const status = rdap?.status?.[0] || "allocated";

    // Format raw WHOIS text banner
    const rawWhois = [
      `# IPRadar.io WHOIS & RDAP Gateway`,
      `# IP Address: ${targetIp} ${resolvedDomain ? `(Resolved from ${resolvedDomain})` : ""}`,
      `# Query Time: ${new Date().toUTCString()}`,
      ``,
      `NetRange:       ${startAddress} - ${endAddress}`,
      `CIDR:           ${cidr}`,
      `NetName:        ${netName}`,
      `NetHandle:      ${handle}`,
      `NetType:        ${rdap?.type || "Direct Allocation"}`,
      `Status:         ${status}`,
      `OriginAS:       AS${asn}`,
      `Organization:   ${org}`,
      `ISP:            ${isp}`,
      `Hostname:       ${hostname || "None recorded"}`,
      `Country:        ${country} (${countryCode})`,
      `City:           ${city}`,
      `Postal:         ${ipwho?.postal || "N/A"}`,
      `Timezone:       ${ipwho?.timezone?.id || "UTC"} (${ipwho?.timezone?.utc || "+00:00"})`,
      `Coordinates:    ${ipwho?.latitude || 0}, ${ipwho?.longitude || 0}`,
    ].join("\n");

    return NextResponse.json({
      success: true,
      ip: targetIp,
      domain: resolvedDomain,
      hostname,
      netName,
      handle,
      startAddress,
      endAddress,
      cidr,
      status,
      asn,
      org,
      isp,
      country,
      countryCode,
      city,
      rawWhois,
    });
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : "WHOIS query failed";
    return NextResponse.json({ success: false, error: errorMsg }, { status: 500 });
  }
}
