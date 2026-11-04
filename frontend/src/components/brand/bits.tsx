/** Small pieces shared by the Brand page tabs. */

const STATUS_STYLES: Record<string, string> = {
  current: "bg-emerald-50 text-emerald-800",
  replaced: "bg-amber-50 text-amber-800",
  draft: "bg-sky-50 text-sky-800",
  archived: "bg-stone-100 text-stone-600",
  unclear: "bg-red-50 text-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLES[status] ?? ""}`}>{status}</span>;
}

export function Quote({ text }: { text: string }) {
  return <q className="ml-2 text-stone-500">{text}</q>;
}

export function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <p>
      <span className="mr-2 inline-block min-w-28 text-xs font-medium uppercase tracking-wide text-stone-400">
        {label}
      </span>
      {children}
    </p>
  );
}
