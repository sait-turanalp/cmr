import { NextResponse } from "next/server";
import { getToken } from "next-auth/jwt";

// Suspicious patterns to block (path traversal, system files, etc.)
const BLOCKED_PATTERNS = [
  /\/\.\./,           // Path traversal
  /\/dev\//,          // System device files
  /\/etc\//,          // System config files
  /\/proc\//,         // Process files
  /^\/\/+/,           // Multiple slashes
  /\0/,               // Null bytes
  /\\x[0-9a-f]{2}/i,  // Hex encoded chars
];

// Block known bad user agents (scanners, exploit tools)
const BAD_USER_AGENTS = [
  /nmap/i,
  /nikto/i,
  /sqlmap/i,
  /masscan/i,
  /zgrab/i,
];

function isBlockedRequest(req: Request): boolean {
  const url = new URL(req.url);
  const pathname = url.pathname;
  const userAgent = req.headers.get("user-agent") || "";

  // Check for blocked path patterns
  for (const pattern of BLOCKED_PATTERNS) {
    if (pattern.test(pathname)) {
      console.warn(`Blocked suspicious path: ${pathname}`);
      return true;
    }
  }

  // Check for bad user agents
  for (const pattern of BAD_USER_AGENTS) {
    if (pattern.test(userAgent)) {
      console.warn(`Blocked bad user agent: ${userAgent}`);
      return true;
    }
  }

  return false;
}

export async function middleware(req: Request) {
  const pathname = new URL(req.url).pathname;
  // Yalnizca salt-okunur yoklama uclari korumasiz kalir; bunlar saniyede ~2 kez
  // cagriliyor ve sadece sayac bilgisi donuyor, o yuzden getToken() maliyetini
  // buraya eklemiyoruz (uretim hizi etkilenmesin).
  // KORUNANLAR: /api/proxy/process-pdf (CPU tuketir) ve /api/proxy/download
  // (uretilen dosya). Oncesinde tum /api/proxy acikti — giris yapmamis herkes
  // PDF urettirip sunucuyu mesgul edebiliyordu.
  const unprotectedRoutes = [
    "/api/auth",
    "/api/proxy/progress",
    "/api/proxy/active",
    "/api/proxy/isfree",
  ];

  // Unprotected route'lar JWT decrypt'e girmez — progress polling saniyede 2
  // istek atiyor, her birinde JWE decrypt gereksiz maliyet.
  if (unprotectedRoutes.some((route) => pathname.startsWith(route))) {
    return NextResponse.next();
  }

  const secret = process.env.NEXTAUTH_SECRET;
  // @ts-ignore error-bypass
  const token = await getToken({ req, secret });

  if (!token && isBlockedRequest(req)) {
    return new NextResponse(
      JSON.stringify({ error: "Bad Request" }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }

  if (!token) {
    // API cagrilarinda yonlendirme yerine 401: istemci JSON bekliyor, HTML
    // gelirse parse hatasi aliyor. Sayfa isteklerinde yonlendirme dogru.
    if (pathname.startsWith("/api/")) {
      return new NextResponse(
        JSON.stringify({ error: "Unauthorized" }),
        { status: 401, headers: { "Content-Type": "application/json" } }
      );
    }
    return NextResponse.redirect(new URL("/", req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/api/:path*",
  ],
};
