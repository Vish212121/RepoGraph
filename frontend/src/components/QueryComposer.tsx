interface QueryComposerProps {
  question: string;
  loading: boolean;
  onQuestionChange: (question: string) => void;
  onSubmit: () => void;
  memory?: boolean;
}

export default function QueryComposer({ question, loading, onQuestionChange, onSubmit, memory }: QueryComposerProps) {
  return (
    <div className="composer">
      <textarea
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); onSubmit(); }
        }}
        placeholder={memory ? "Search saved findings by topic or file…" : "Ask about contributors, commits, files, or repository history…"}
        rows={2}
        aria-label={memory ? "Memory search" : "Repository question"}
      />
      <button className="ask-button" onClick={onSubmit} disabled={loading || !question.trim()}>
        {loading ? "Waiting…" : memory ? "Recall findings" : "Trace answer"}
        <span aria-hidden="true">↗</span>
      </button>
    </div>
  );
}
