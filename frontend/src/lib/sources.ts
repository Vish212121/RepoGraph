// Repository and model-provided URLs are untrusted. Never permit executable schemes.
export function safeSource(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

export function sourceLabel(value: string): string {
  const url = new URL(value);
  const parts = url.pathname.split("/").filter(Boolean);
  const commit = parts.indexOf("commit");
  if (commit >= 0) return `Commit ${parts[commit + 1]?.slice(0, 8) ?? "source"}`;
  const blob = parts.indexOf("blob");
  if (blob >= 0) return parts.slice(blob + 2).join("/") || "File source";
  return `${url.hostname}${url.pathname === "/" ? "" : url.pathname}`;
}
