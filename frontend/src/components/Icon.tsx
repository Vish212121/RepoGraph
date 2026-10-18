export type IconName = "graph" | "memory" | "arrow" | "file" | "commit" | "person" | "source" | "close" | "menu" | "list" | "focus" | "search" | "code" | "overview";
const paths: Record<IconName, React.ReactNode> = {
  graph: <><path d="m7 7 10 3M7 7l4 11m6-8-6 8"/><circle cx="6" cy="6" r="3"/><circle cx="18" cy="10" r="3"/><circle cx="11" cy="19" r="3"/></>,
  memory: <><path d="M7 4h10a2 2 0 0 1 2 2v16l-7-4-7 4V6a2 2 0 0 1 2-2Z"/><path d="M9 9h6m-6 4h4"/></>,
  arrow: <><path d="M5 12h14m-6-6 6 6-6 6"/></>,
  file: <><path d="M14 3H6v18h12V7l-4-4Zm0 0v5h4M9 12h6m-6 4h4"/></>,
  commit: <><path d="M3 12h5m8 0h5"/><circle cx="12" cy="12" r="4"/></>,
  person: <><circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
  source: <><path d="M14 3h7v7m0-7L10 14M10 5H4v16h16v-6"/></>,
  close: <path d="m6 6 12 12M6 18 18 6"/>,
  menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
  list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.1M3 12h.1M3 18h.1"/>,
  focus: <><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/><circle cx="12" cy="12" r="3"/></>,
  search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
  code: <path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>,
  overview: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
};
export default function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
