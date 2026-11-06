export interface IpData {
  ip: string;
  type: string;
  success: boolean;
  continent?: string;
  continent_code?: string;
  country: string;
  country_code: string;
  region: string;
  region_code?: string;
  city: string;
  latitude: number;
  longitude: number;
  postal: string;
  calling_code?: string;
  capital?: string;
  flag?: {
    img?: string;
    emoji?: string;
  };
  connection: {
    asn: number | string;
    org: string;
    isp: string;
    domain?: string;
  };
  timezone: {
    id: string;
    abbr?: string;
    is_dst?: boolean;
    offset?: number;
    utc: string;
  };
  ipv6?: string | null;
}

export const DEFAULT_IP_DATA: IpData = {
  ip: "114.12.12.34",
  type: "IPv4",
  success: true,
  continent: "Asia",
  continent_code: "AS",
  country: "Indonesia",
  country_code: "ID",
  region: "Jakarta Raya",
  region_code: "JW",
  city: "Jakarta",
  latitude: -6.2146224,
  longitude: 106.8451342,
  postal: "12850",
  calling_code: "62",
  capital: "Jakarta",
  flag: {
    img: "https://cdn.ipwhois.io/flags/id.svg",
    emoji: "🇮🇩",
  },
  connection: {
    asn: 4761,
    org: "IOH B2B",
    isp: "IOH B2B",
    domain: "ioh.co.id",
  },
  timezone: {
    id: "Asia/Jakarta",
    abbr: "WIB",
    utc: "+07:00",
  },
  ipv6: null,
};
