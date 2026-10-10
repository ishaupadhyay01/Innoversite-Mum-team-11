import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Activity,
  Bell,
  BookOpen,
  ClipboardCheck,
  FileStack,
  GitCompareArrows,
  LayoutDashboard,
  Menu,
  Moon,
  Scale,
  Search,
  Sun,
  Table2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useTheme } from "../../hooks/useTheme";
import { api } from "../../services/api";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/search", label: "Regulatory search", icon: Search },
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/whats-new", label: "What's new", icon: GitCompareArrows },
  { to: "/impact", label: "Impact analysis", icon: Table2 },
  { to: "/checklist", label: "Compliance checklist", icon: ClipboardCheck },
  { to: "/rules", label: "Rules", icon: Scale },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/system", label: "System health", icon: Activity },
];

function Brand() {
  return (
    <div className="flex items-center gap-3 px-5 py-5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="7" fill="rgb(var(--navy-soft))" />
        <circle cx="16" cy="16" r="8.5" fill="none" stroke="#2BB3B1" strokeWidth="2.5" />
        <circle cx="16" cy="16" r="3.2" fill="#F5F7FA" />
      </svg>
      <div className="leading-tight">
        <div className="text-[17px] font-semibold text-white">Reg IRIS</div>
        <div className="text-xs text-slate-400">Regulatory repository &amp; impact scanner</div>
      </div>
    </div>
  );
}

function Sidebar({ unread, onNavigate }: { unread: number; onNavigate?: () => void }) {
  return (
    <nav className="flex h-full flex-col bg-navy" aria-label="Main">
      <Brand />
      <ul className="mt-2 flex-1 space-y-0.5 px-3">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-[14.5px] transition-colors",
                  isActive ? "bg-navy-soft text-white" : "text-slate-300 hover:bg-navy-soft/60 hover:text-white",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={clsx("h-[18px] w-[18px]", isActive ? "text-[#2BB3B1]" : "text-slate-400")} aria-hidden />
                  <span className="flex-1">{label}</span>
                  {to === "/alerts" && unread > 0 && (
                    <span className="rounded-full bg-[#2BB3B1] px-1.5 text-xs font-semibold text-navy">{unread}</span>
                  )}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="border-t border-white/10 px-5 py-4 text-xs leading-relaxed text-slate-400">
        <BookOpen className="mb-1 h-4 w-4" aria-hidden />
        Prototype on synthetic data. Findings support review; they are not legal advice and nothing is filed with regulators.
      </div>
    </nav>
  );
}

export function AppLayout() {
  const [theme, toggleTheme] = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const lastAlertId = useRef<number | null | undefined>(undefined);

  const unreadQuery = useQuery({ queryKey: ["alerts", "unread"], queryFn: api.unreadCount, refetchInterval: 5000 });
  const unread = unreadQuery.data?.unread ?? 0;

  // Mock live notification: when a new alert id appears while the app is open, pop a toast.
  useEffect(() => {
    const latest = unreadQuery.data?.latest_id;
    if (latest === undefined) return;
    if (lastAlertId.current !== undefined && latest !== null && latest !== lastAlertId.current) {
      api
        .alerts({ page_size: 1 })
        .then((page) => {
          const alert = page.items[0];
          if (alert && !alert.is_read) {
            toast(`${alert.change_type}: ${alert.document_name}`, {
              description: alert.summary.slice(0, 140),
              action: { label: "Open", onClick: () => navigate(`/whats-new?alert=${alert.id}`) },
              duration: 10000,
            });
          }
        })
        .catch(() => undefined);
    }
    lastAlertId.current = latest;
  }, [unreadQuery.data?.latest_id, navigate]);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 flex-none lg:block">
        <Sidebar unread={unread} />
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button className="absolute inset-0 bg-navy/50" aria-label="Close menu" onClick={() => setMobileOpen(false)} />
          <div className="relative h-full w-64">
            <Sidebar unread={unread} onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur lg:px-8">
          <button className="rounded p-1.5 text-muted hover:bg-sunken lg:hidden" onClick={() => setMobileOpen((v) => !v)} aria-label="Open menu">
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          {location.pathname !== "/search" && (
            <form onSubmit={submit} className="relative max-w-md flex-1" role="search">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" aria-hidden />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search regulations, e.g. Counterparty LEI"
                aria-label="Search regulations"
                className="h-9 w-full rounded-md border border-line bg-canvas pl-9 pr-3 text-sm placeholder:text-faint focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
              />
            </form>
          )}
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={toggleTheme}
              className="rounded-md p-2 text-muted hover:bg-sunken hover:text-ink"
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
            </button>
            <NavLink to="/alerts" className="relative rounded-md p-2 text-muted hover:bg-sunken hover:text-ink" aria-label={`Alerts, ${unread} unread`}>
              <Bell className="h-[18px] w-[18px]" />
              {unread > 0 && (
                <span className="absolute right-1 top-1 min-w-[16px] rounded-full bg-fail px-1 text-center text-[10px] font-semibold leading-4 text-white">
                  {unread}
                </span>
              )}
            </NavLink>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1320px] flex-1 px-4 py-7 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
