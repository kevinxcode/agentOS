const panels = [
  {
    title: "Tasks",
    empty: "No tasks yet",
    detail: "Create and track work here when task orchestration is enabled.",
  },
  {
    title: "Running Agents",
    empty: "No agents are running",
    detail: "Active agent sessions will appear here.",
  },
  {
    title: "Pending Approvals",
    empty: "Nothing is awaiting approval",
    detail: "Changes that require your decision will be listed here.",
  },
  {
    title: "Provider Health",
    empty: "No providers configured",
    detail: "Provider connections and health checks will appear after setup.",
  },
] as const;

export default function DashboardPage() {
  return (
    <main className="mission-control">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Workspace overview</p>
          <h1>Mission Control</h1>
        </div>
        <p className="quiet-status"><span aria-hidden="true" />Ready for setup</p>
      </div>
      <div className="panel-grid">
        {panels.map((panel) => (
          <section className="status-panel" key={panel.title} aria-labelledby={`${panel.title.replaceAll(" ", "-").toLowerCase()}-heading`}>
            <h2 id={`${panel.title.replaceAll(" ", "-").toLowerCase()}-heading`}>{panel.title}</h2>
            <div className="empty-state">
              <span className="empty-glyph" aria-hidden="true">○</span>
              <h3>{panel.empty}</h3>
              <p>{panel.detail}</p>
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
