import { useState } from "react";
import { Check, Database, X } from "lucide-react";
import type { PendingSQLBlock } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

interface SqlApprovalCardProps {
  block: PendingSQLBlock;
  onDecision: (approved: boolean) => Promise<void>;
}

// Human-in-the-loop gate: the backend paused the LangGraph run with interrupt() and handed
// us the generated SQL. Nothing runs against the database until the user approves here.
export function SqlApprovalCard({ block, onDecision }: SqlApprovalCardProps) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);

  async function decide(approved: boolean) {
    setBusy(approved ? "approve" : "reject");
    try {
      await onDecision(approved);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="border-amber-500/30 bg-amber-500/5">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-amber-400">
          <Database className="h-4 w-4" />
          Approval required before running SQL
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {block.explanation && (
          <p className="text-sm text-muted-foreground">{block.explanation}</p>
        )}
        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs leading-relaxed">
          <code>{block.sql}</code>
        </pre>
        <div className="flex gap-2">
          <Button size="sm" disabled={busy !== null} onClick={() => decide(true)}>
            {busy === "approve" ? <Spinner /> : <Check className="h-4 w-4" />}
            Approve &amp; run
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null}
            onClick={() => decide(false)}
          >
            {busy === "reject" ? <Spinner /> : <X className="h-4 w-4" />}
            Reject
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
