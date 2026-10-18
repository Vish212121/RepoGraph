import type { QueryResponse } from "../types";
import Markdown from "react-markdown";
import { safeSource } from "../lib/sources";

export default function AnswerPanel({
  result,
  onSaveFinding,
  saving,
  saved,
  savedLabel,
}: {
  result: QueryResponse;
  onSaveFinding?: () => void;
  saving?: boolean;
  saved?: boolean;
  savedLabel?: string;
}) {
  return (
    <article className="panel answer-panel">
      <div className="panel-heading">
        <span className="panel-kicker">{result.intent === "recall_context" ? "RECALLED CONTEXT" : "THE SHORT ANSWER"}</span>
        <span className="panel-icon">✦</span>
      </div>
      <div className="answer-copy"><Markdown skipHtml urlTransform={value => safeSource(value) ?? ""} components={{ img: () => null, a: ({ children, href }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span> }}>{result.answer}</Markdown></div>
      {result.limitation && <div className="limitation"><strong>Limitation:</strong> {result.limitation}</div>}
      {onSaveFinding && result.evidence && result.evidence.tool_name !== "recall_context" && (
        <button className="save-finding-button" onClick={onSaveFinding} disabled={saving || saved}>
          {saved ? (savedLabel ?? "Saved to memory") : saving ? "Saving finding…" : "Save finding"}
        </button>
      )}
      <div className="answer-footer">
        <span>{result.model ?? (result.intent === "recall_context" ? "Persistent memory" : "Deterministic evidence")}</span>
        <span>{result.intent === "recall_context" ? "Previously saved context" : result.used_fallback ? "Fallback summary" : "Model-generated explanation"}</span>
      </div>
    </article>
  );
}
