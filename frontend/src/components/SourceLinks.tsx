import { safeSource, sourceLabel } from "../lib/sources";
import Icon from "./Icon";

export default function SourceLinks({ urls }: { urls: unknown[] }) {
  const safe = [...new Set(urls.map(safeSource).filter((url): url is string => Boolean(url)))];
  return <div className="source-links">{safe.length ? safe.map(url => (
    <a key={url} href={url} target="_blank" rel="noopener noreferrer" title={url}><Icon name="source" size={14}/><span>{sourceLabel(url)}</span></a>
  )) : <p className="muted">No source URL returned for this selection.</p>}</div>;
}
