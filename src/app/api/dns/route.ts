import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const name = searchParams.get("name")?.trim();
    const type = (searchParams.get("type") || "A").toUpperCase();

    if (!name) {
      return NextResponse.json(
        { error: "Domain or IP name is required" },
        { status: 400 }
      );
    }

    // Sanitize host
    const sanitized = name.replace(/^https?:\/\//i, "").split("/")[0].split(":")[0].trim();

    const dohUrl = `https://dns.google/resolve?name=${encodeURIComponent(sanitized)}&type=${encodeURIComponent(type)}`;
    const res = await fetch(dohUrl, {
      headers: {
        Accept: "application/json",
      },
      next: { revalidate: 30 },
    });

    if (!res.ok) {
      throw new Error(`DNS resolution failed with status ${res.status}`);
    }

    const data = await res.json();

    return NextResponse.json({
      name: sanitized,
      type,
      status: data.Status,
      answers: (data.Answer || []).map((ans: { name: string; type: number; TTL: number; data: string }) => ({
        name: ans.name,
        type: ans.type,
        ttl: ans.TTL,
        data: ans.data,
      })),
      authority: data.Authority || [],
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "DNS resolution error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
