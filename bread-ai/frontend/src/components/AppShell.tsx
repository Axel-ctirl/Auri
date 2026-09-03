/** Application chrome: navigation rail, header status and the routed outlet. */

import {
  Activity,
  BookOpen,
  Boxes,
  Cpu,
  Database,
  FileText,
  Info,
  Menu,
  MessageSquare,
  MessagesSquare,
  Settings as SettingsIcon,
  ShieldAlert,
  X,
} from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useModelStatus, useSystemStatus } from "../api/hooks";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Chat", icon: <MessageSquare className="h-4 w-4" />, end: true },
  { to: "/conversations", label: "Conversations", icon: <MessagesSquare className="h-4 w-4" /> },
  { to: "/knowledge-spaces", label: "Knowledge Spaces", icon: <Boxes className="h-4 w-4" /> },
  { to: "/documents", label: "Documents", icon: <FileText className="h-4 w-4" /> },
  { to: "/training", label: "Training", icon: <Activity className="h-4 w-4" /> },
  { to: "/datasets", label: "Datasets", icon: <Database className="h-4 w-4" /> },
  { to: "/models", label: "Models", icon: <Cpu className="h-4 w-4" /> },
  { to: "/settings", label: "Settings", icon: <SettingsIcon className="h-4 w-4" /> },
  { to: "/api-docs", label: "API Docs", icon: <BookOpen className="h-4 w-4" /> },
  { to: "/about", label: "About", icon: <Info className="h-4 w-4" /> },
];

function ModelPill() {
  const { data: status } = useModelStatus();

  if (!status) {
    return <span className="badge">checking model…</span>;
  }
  if (!status.loaded) {
    return (
      <span className="badge border-amber-900/60 text-amber-300">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden />
        no model loaded
      </span>
    );
  }
  return (
    <span className="badge border-emerald-900/60 text-emerald-300">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
      {status.model_id ?? status.backend}
    </span>
  );
}

function LanWarning() {
  const { data } = useSystemStatus(60_000);
  if (!data?.binds_to_lan) return null;

  return (
    <div className="flex items-center gap-2 border-b border-amber-900/60 bg-amber-950/40 px-4 py-2 text-xs text-amber-200">
      <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden />
      <span>
        Bread is bound to {data.host}, which is reachable from your network. An API key is
        required, and there is no transport encryption without a reverse proxy.
      </span>
    </div>
  );
}

export default function AppShell() {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-ink-950">
      {/* Backdrop for the mobile drawer. */}
      {navOpen && (
        <button
          type="button"
          className="fixed inset-0 z-20 bg-black/60 md:hidden"
          onClick={() => setNavOpen(false)}
          aria-label="Close navigation"
        />
      )}

      <nav
        className={`fixed inset-y-0 left-0 z-30 flex w-60 shrink-0 flex-col border-r
          border-ink-800 bg-ink-900 transition-transform md:static md:translate-x-0
          ${navOpen ? "translate-x-0" : "-translate-x-full"}`}
        aria-label="Main"
      >
        <div className="flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <span
              className="flex h-8 w-8 items-center justify-center rounded-lg
                bg-gradient-to-br from-crust-300 to-crust-600 text-base"
              aria-hidden
            >
              🍞
            </span>
            <div>
              <p className="text-sm font-semibold text-ink-100">Bread</p>
              <p className="text-[11px] text-ink-500">local coding assistant</p>
            </div>
          </div>
          <button
            type="button"
            className="rounded p-1 text-ink-400 hover:bg-ink-800 md:hidden"
            onClick={() => setNavOpen(false)}
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-4">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                onClick={() => setNavOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? "bg-ink-800 font-medium text-crust-200"
                      : "text-ink-300 hover:bg-ink-800/60 hover:text-ink-100"
                  }`
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div className="border-t border-ink-800 px-4 py-3 text-[11px] leading-relaxed text-ink-500">
          Everything stays on this machine. No telemetry, no analytics, no uploads.
        </div>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col">
        <LanWarning />
        <header className="flex items-center justify-between gap-3 border-b border-ink-800 px-4 py-2">
          <button
            type="button"
            className="rounded p-1.5 text-ink-300 hover:bg-ink-800 md:hidden"
            onClick={() => setNavOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="min-w-0 flex-1" />
          <ModelPill />
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
