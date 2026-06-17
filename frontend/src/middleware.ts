import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Helper to decode and verify JWT payload
async function verifyAndParseJwt(token: string) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    
    const [header, payload, signature] = parts;
    const secret = process.env.JWT_SECRET_KEY || 'my_jwt_secret_key_change_me_in_prod';
    
    // Verify signature
    const encoder = new TextEncoder();
    const data = encoder.encode(`${header}.${payload}`);
    const key = await crypto.subtle.importKey(
      'raw',
      encoder.encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['verify']
    );
    
    const signatureStr = atob(signature.replace(/-/g, '+').replace(/_/g, '/'));
    const signatureBytes = new Uint8Array(signatureStr.length);
    for (let i = 0; i < signatureStr.length; i++) {
      signatureBytes[i] = signatureStr.charCodeAt(i);
    }
    
    const isValid = await crypto.subtle.verify('HMAC', key, signatureBytes, data);
    if (!isValid) return null;
    
    // Decode base64 payload
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  // Public paths that don't require authentication
  const isPublicPath = pathname === '/login' || pathname === '/register' || pathname === '/verify-email';
  
  // Get token from cookies
  const token = request.cookies.get('access_token')?.value;

  // 1. If trying to access protected route without token, redirect to login
  if (!token && !isPublicPath) {
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    return NextResponse.redirect(url);
  }

  // 2. If trying to access auth pages while already logged in, redirect to home
  if (token && isPublicPath) {
    const url = request.nextUrl.clone();
    url.pathname = '/';
    return NextResponse.redirect(url);
  }

  // 3. Role-based access control for logged-in users
  if (token) {
    const payload = await verifyAndParseJwt(token);
    
    if (payload && payload.role) {
      const role = payload.role;
      
      // Admin only routes
      const isAdminRoute = pathname.startsWith('/repos') || pathname.startsWith('/settings');
      
      if (isAdminRoute && (role === 'analyst' || role === 'viewer')) {
        // Redirect unauthorized users to dashboard
        const url = request.nextUrl.clone();
        url.pathname = '/';
        return NextResponse.redirect(url);
      }
    }
  }

  return NextResponse.next();
}

// Specify which routes the middleware should run on
export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
};
