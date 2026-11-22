import { NextResponse, type NextRequest } from "next/server";

const TOKEN_COOKIE = "gf_token";
const ROLE_COOKIE = "gf_role";

// Which roles may open each area. The API enforces permissions again on every call;
// this only keeps people out of screens they can't use.
const AREAS: { prefix: string; roles: string[] }[] = [
  { prefix: "/platform", roles: ["platform_admin"] },
  { prefix: "/dashboard", roles: ["gym_owner", "gym_manager", "trainer", "platform_admin"] },
  { prefix: "/editor", roles: ["gym_owner", "gym_manager", "platform_admin"] },
  { prefix: "/kiosk", roles: ["gym_owner", "gym_manager", "trainer"] },
  { prefix: "/member", roles: ["member"] },
];

function home(role: string | undefined) {
  if (role === "platform_admin") return "/platform/admin/dashboard";
  if (role === "member") return "/member/dashboard";
  if (role === "trainer") return "/dashboard/members";
  return "/dashboard/overview";
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get(TOKEN_COOKIE)?.value;
  const role = req.cookies.get(ROLE_COOKIE)?.value;

  if (["/login", "/register", "/"].includes(pathname) && token) {
    return NextResponse.redirect(new URL(home(role), req.url));
  }

  const area = AREAS.find((a) => pathname.startsWith(a.prefix));
  if (!area) return NextResponse.next();

  if (!token) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (!role || !area.roles.includes(role)) {
    return NextResponse.redirect(new URL(home(role), req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/login", "/register", "/platform/:path*", "/dashboard/:path*", "/editor/:path*", "/member/:path*", "/kiosk"],
};
