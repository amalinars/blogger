"use client";

import React, { useState } from "react";
import { ExternalLink, Navigation, MapPin, ZoomIn, ZoomOut, RefreshCw } from "lucide-react";
import { IpData } from "@/lib/types";

interface IpMapProps {
  data: IpData;
}

export function IpMap({ data }: IpMapProps) {
  const [zoom, setZoom] = useState(0.06);

  const lat = data.latitude || -6.2146;
  const lon = data.longitude || 106.8451;

  const minLon = lon - zoom;
  const maxLon = lon + zoom;
  const minLat = lat - zoom;
  const maxLat = lat + zoom;

  // OpenStreetMap embed URL with exact coordinates
  const osmUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${minLon}%2C${minLat}%2C${maxLon}%2C${maxLat}&layer=mapnik&marker=${lat}%2C${lon}`;
  const googleMapsUrl = `https://www.google.com/maps?q=${lat},${lon}`;

  return (
    <div className="rounded-2xl bg-[#091326]/90 border border-slate-700/60 overflow-hidden shadow-2xl flex flex-col justify-between">
      {/* Header */}
      <div className="p-4 sm:p-5 border-b border-slate-800 bg-[#070e1c] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h3 className="text-sm sm:text-base font-bold text-white flex items-center gap-2">
            <Navigation className="w-4 h-4 text-cyan-400" />
            <span>Approximate IP Address Location</span>
          </h3>
          <p className="text-[11px] text-slate-400">
            Coordinates: {lat.toFixed(4)}°, {lon.toFixed(4)}°
          </p>
        </div>

        <a
          href="#report-correction"
          className="text-xs text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 font-medium"
        >
          <span>Location not correct? Report correction</span>
          <span className="text-[10px]">→</span>
        </a>
      </div>

      {/* Map Area */}
      <div className="relative w-full h-[340px] sm:h-[380px] bg-[#0c1527] overflow-hidden group">
        <iframe
          title="IP Location Map"
          src={osmUrl}
          className="w-full h-full border-0 filter contrast-[1.05] brightness-[0.92]"
          loading="lazy"
        />

        {/* Map Overlay Button (Open in Maps ↗ - exactly like in screenshot) */}
        <div className="absolute top-3 left-3 z-10">
          <a
            href={googleMapsUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg bg-white/95 hover:bg-white text-slate-900 font-semibold text-xs shadow-lg backdrop-blur flex items-center gap-1.5 transition-all hover:scale-105 active:scale-95"
          >
            <span>Open in Maps</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>

        {/* Zoom Controls */}
        <div className="absolute top-3 right-3 z-10 flex flex-col gap-1.5 bg-[#091326]/90 p-1 rounded-lg border border-slate-700/80 shadow-md backdrop-blur">
          <button
            onClick={() => setZoom((z) => Math.max(0.015, z / 1.5))}
            className="p-1 text-slate-300 hover:text-white hover:bg-slate-700/60 rounded transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.min(0.3, z * 1.5))}
            className="p-1 text-slate-300 hover:text-white hover:bg-slate-700/60 rounded transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
        </div>

        {/* Bottom Location Badge Overlay */}
        <div className="absolute bottom-3 left-3 right-3 z-10 flex items-center justify-between gap-2 p-2.5 rounded-xl bg-[#091326]/85 border border-slate-700/80 backdrop-blur-md text-xs">
          <div className="flex items-center gap-2 truncate">
            <MapPin className="w-4 h-4 text-rose-500 shrink-0 animate-bounce" />
            <span className="font-semibold text-slate-100 truncate">
              {data.city}, {data.region}, {data.country}
            </span>
          </div>
          <span className="text-[11px] text-slate-400 shrink-0 font-mono">
            {data.postal}
          </span>
        </div>
      </div>

      {/* Footer Info */}
      <div className="p-3 bg-[#070e1c] text-[11px] text-slate-400 border-t border-slate-800 text-center">
        IP Geolocation is approximate to city/district level and does not expose exact street addresses.
      </div>
    </div>
  );
}
