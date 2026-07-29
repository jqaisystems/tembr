export default function HelpPanel({ children }: { children: React.ReactNode }) {
  return (
    <details className="help">
      <summary>How this screen works</summary>
      <div className="help-body">{children}</div>
    </details>
  );
}
