import type { ReactNode } from "react";
import { Activity, FileText, GitBranch, RefreshCw, Search } from "lucide-react";
import type { ChatResponse } from "@/api/types";
import { Badge } from "@/components/ui/badge";

function Section({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {icon}
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function YesNo({ value }: { value: boolean }) {
  return (
    <Badge variant={value ? "success" : "secondary"}>{value ? "yes" : "no"}</Badge>
  );
}

export function TracePanel({ response }: { response: ChatResponse | null }) {
  if (!response) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-foreground">
        Select an answer to inspect how the pipeline produced it.
      </div>
    );
  }

  const { metadata: m } = response;

  return (
    <div className="space-y-6 overflow-y-auto p-4">
      <div>
        <h2 className="text-sm font-semibold">Pipeline trace</h2>
        <p className="text-xs text-muted-foreground">What ran to produce this answer</p>
      </div>

      <Section icon={<GitBranch className="h-3.5 w-3.5" />} title="Routing & cost">
        <Row label="Route" value={<Badge variant="outline">{m.route}</Badge>} />
        <Row label="Confidence" value={`${Math.round(response.confidence * 100)}%`} />
        <Row label="Cache hit" value={<YesNo value={response.cache_hit} />} />
        <Row label="Cost saved" value={response.cost_saved} />
      </Section>

      <Section icon={<Activity className="h-3.5 w-3.5" />} title="CRAG (corrective)">
        <Row label="Triggered" value={<YesNo value={m.crag_triggered} />} />
        <Row
          label="Relevance score"
          value={m.crag_relevance_score != null ? m.crag_relevance_score.toFixed(2) : "—"}
        />
      </Section>

      <Section icon={<RefreshCw className="h-3.5 w-3.5" />} title="Self-RAG (reflection)">
        <Row label="Iterations" value={m.reflection_iterations} />
        <Row
          label="Reflection score"
          value={m.reflection_score != null ? m.reflection_score.toFixed(2) : "—"}
        />
        {m.refined_question && (
          <p className="rounded-md bg-muted p-2 text-xs italic text-muted-foreground">
            Refined: “{m.refined_question}”
          </p>
        )}
      </Section>

      <Section
        icon={<Search className="h-3.5 w-3.5" />}
        title={`Retrieved chunks (${m.retrieved_chunks.length})`}
      >
        {m.retrieved_chunks.length === 0 ? (
          <p className="text-sm text-muted-foreground">No chunks recorded.</p>
        ) : (
          <div className="space-y-2">
            {m.retrieved_chunks.map((c, i) => (
              <div key={i} className="rounded-md border bg-card p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-medium" title={c.source}>
                    {c.source || "unknown"}
                  </span>
                  <Badge variant="outline">{c.score.toFixed(3)}</Badge>
                </div>
                <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{c.text}</p>
              </div>
            ))}
          </div>
        )}
      </Section>

      {response.sources.length > 0 && (
        <Section icon={<FileText className="h-3.5 w-3.5" />} title="Sources">
          <ul className="space-y-1">
            {response.sources.map((s, i) => (
              <li key={i} className="truncate text-xs text-muted-foreground" title={s}>
                • {s}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
