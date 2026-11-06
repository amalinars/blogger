import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const isPing = searchParams.has("ping");
  const isDownload = searchParams.has("download");

  // Ping endpoint
  if (isPing) {
    return NextResponse.json(
      { timestamp: Date.now() },
      {
        headers: {
          "Cache-Control": "no-store, no-cache, must-revalidate",
          Pragma: "no-cache",
        },
      }
    );
  }

  // Download test: generates binary chunk with no-store
  if (isDownload) {
    const size = Math.min(
      Math.max(parseInt(searchParams.get("size") || "2500000", 10), 200000),
      8000000
    );
    const buffer = new Uint8Array(size);
    for (let i = 0; i < size; i += 128) {
      buffer[i] = (i % 255);
    }

    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Length": size.toString(),
        "Cache-Control": "no-store, no-cache, must-revalidate",
        Pragma: "no-cache",
      },
    });
  }

  return NextResponse.json({ status: "ok" });
}

export async function POST(request: NextRequest) {
  try {
    const reader = request.body?.getReader();
    let totalBytes = 0;

    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) totalBytes += value.length;
      }
    }

    return NextResponse.json(
      { receivedBytes: totalBytes, timestamp: Date.now() },
      {
        headers: {
          "Cache-Control": "no-store, no-cache, must-revalidate",
        },
      }
    );
  } catch {
    return NextResponse.json({ error: "Upload failed" }, { status: 400 });
  }
}
