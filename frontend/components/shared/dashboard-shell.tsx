"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GraduationCap, LogOut, Menu, X, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface DashboardNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Exact-match this route instead of prefix-match (use for the root overview page). */
  exact?: boolean;
}

export function initialsFrom(name: string | undefined, email: string | undefined): string {
  if (name && name.trim().length > 0) {
    const parts = name.trim().split(/\s+/);
    const first = parts[0]?.[0] ?? "";
    const second = parts[1]?.[0] ?? "";
    return (first + second).toUpperCase() || "?";
  }
  return (email?.[0] ?? "?").toUpperCase();
}

export function DashboardShell({
  children,
  navItems,
  displayName,
  initials,
  profileHref,
  onLogout,
  contentClassName,
}: {
  children: React.ReactNode;
  navItems: DashboardNavItem[];
  displayName: string;
  initials: string;
  profileHref?: string;
  onLogout: () => void;
  /** Extra classes for the content column (e.g. `min-w-0` to contain wide tables). */
  contentClassName?: string;
}) {
  const pathname = usePathname();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const renderNav = (onNavigate?: () => void) =>
    navItems.map((item) => {
      const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
      const Icon = item.icon;
      return (
        <Link
          key={item.href}
          href={item.href}
          onClick={onNavigate}
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
            active
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:bg-brand-light hover:text-brand-dark"
          )}
          aria-current={active ? "page" : undefined}
        >
          <Icon className="h-4 w-4 shrink-0" />
          {item.label}
        </Link>
      );
    });

  const brand = (compact = false) => (
    <div className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <GraduationCap className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <span className="block font-display text-lg font-semibold leading-tight tracking-tight">PLACER</span>
        {!compact && (
          <span className="block text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
            Recruitment Intelligence
          </span>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar — desktop */}
      <aside className="hidden w-64 shrink-0 border-r border-border bg-card lg:flex lg:flex-col">
        <div className="flex h-16 items-center border-b border-border px-6">{brand()}</div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-4">{renderNav()}</nav>
        <div className="border-t border-border p-4 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">PLACER</span> · AI assessment platform
        </div>
      </aside>

      {/* Sidebar — mobile overlay */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-950/60" onClick={() => setMobileNavOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-border bg-card shadow-elevated">
            <div className="flex h-16 items-center justify-between border-b border-border px-5">
              {brand(true)}
              <button
                onClick={() => setMobileNavOpen(false)}
                aria-label="Close menu"
                className="rounded-md p-1 text-muted-foreground hover:bg-brand-light hover:text-brand-dark"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="flex-1 space-y-1 overflow-y-auto p-4">{renderNav(() => setMobileNavOpen(false))}</nav>
          </aside>
        </div>
      )}

      <div className={cn("flex flex-1 flex-col", contentClassName)}>
        {/* Topbar */}
        <header className="flex h-16 items-center justify-between border-b border-border bg-card px-4 shadow-sm lg:px-8">
          <div className="flex items-center gap-3">
            <button
              className="rounded-md p-1.5 text-muted-foreground hover:bg-brand-light hover:text-brand-dark lg:hidden"
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="lg:hidden">{brand(true)}</div>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger className="flex items-center gap-2 rounded-full outline-none focus:ring-2 focus:ring-ring">
              <Avatar>
                <AvatarFallback>{initials}</AvatarFallback>
              </Avatar>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel className="truncate">{displayName}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {profileHref && (
                <DropdownMenuItem asChild>
                  <Link href={profileHref}>Edit profile</Link>
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onSelect={onLogout} className="text-destructive">
                <LogOut className="mr-2 h-4 w-4" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
