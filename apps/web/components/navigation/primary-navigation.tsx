"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

function routeCurrent(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function NavigationLinks({ pathname, mobile = false }: { pathname: string; mobile?: boolean }) {
  return (
    <>
      <Link
        className={`nav-item${routeCurrent(pathname, "/") ? " nav-item-active" : ""}`}
        href="/"
        aria-current={routeCurrent(pathname, "/") ? "page" : undefined}
      >
        Overview
      </Link>
      <Link
        className={`nav-item${routeCurrent(pathname, "/audit") ? " nav-item-active" : ""}`}
        href="/audit"
        aria-current={routeCurrent(pathname, "/audit") ? "page" : undefined}
      >
        Audit
      </Link>
      {!mobile && (
        <>
          <span className="nav-item nav-item-disabled" aria-disabled="true">Tasks · coming soon</span>
          <span className="nav-item nav-item-disabled" aria-disabled="true">Agents · coming soon</span>
          <span className="nav-item nav-item-disabled" aria-disabled="true">Settings · coming soon</span>
        </>
      )}
    </>
  );
}

export function PrimaryNavigation({ pathname: suppliedPathname }: { pathname?: string }) {
  const routePathname = usePathname();
  const pathname = suppliedPathname ?? routePathname;
  return (
    <>
      <nav className="sidebar" aria-label="Primary navigation">
        <NavigationLinks pathname={pathname} />
      </nav>
      <nav className="mobile-navigation" aria-label="Mobile navigation">
        <NavigationLinks pathname={pathname} mobile />
      </nav>
    </>
  );
}
