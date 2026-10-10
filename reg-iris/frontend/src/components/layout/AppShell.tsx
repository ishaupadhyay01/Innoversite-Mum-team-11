import clsx from "clsx";
import { FileStack, GitCompare, LayoutDashboard, Scale, Search } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { AlertBell } from "./AlertBell";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/search", label: "Search", icon: Search },
  { to: "/compare", label: "Compare", icon: GitCompare },
  { to: "/impact", label: "Impact analysis", icon: Scale },
];

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-line bg-white">
        <div className="flex items-center gap-2 px-5 py-5">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <div>
            <div className="text-sm font-semibold leading-tight">Reg IRIS</div>
            <div className="text-[11px] leading-tight text-ink-faint">Regulatory intelligence</div>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm",
                  isActive ? "bg-brand-tint font-medium text-brand" : "text-ink-soft hover:bg-canvas hover:text-ink",
                )
              }
            >
              <Icon className="h-4 w-4" /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4 text-[11px] leading-relaxed text-ink-faint">
          Synthetic data only. Detects gaps; never files with regulators.
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-end border-b border-line bg-white/90 px-6 backdrop-blur">
          <AlertBell />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-soft">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
