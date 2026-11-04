/** Typing straight into an asset: every field of its fixed shape, as plain inputs. */

type Value = string | string[] | Record<string, unknown>[] | Record<string, unknown>;

const LABELS: Record<string, string> = {
  sender: "Sender", subject: "Subject", preview_text: "Preview text", sections: "Sections", heading: "Heading",
  body: "Body", button_text: "Button text", button_link: "Button link", link_text: "Second link text", link_url: "Second link", author: "Author", text: "Text",
  hashtags: "Hashtags (one per line)", title: "Title", date: "Date", kind: "Section type", items: "Items (one per line)",
};

const LONG = new Set(["body", "text"]);

export function FieldsEditor({ value, onChange }: { value: Record<string, Value>; onChange: (v: Record<string, Value>) => void }) {
  return (
    <div className="space-y-3">
      {Object.entries(value).filter(([key]) => key !== "sources").map(([key, field]) => (
        <Field key={key} name={key} value={field} onChange={(v) => onChange({ ...value, [key]: v })} />
      ))}
    </div>
  );
}

function Field({ name, value, onChange }: { name: string; value: Value; onChange: (v: Value) => void }) {
  const label = <span className="text-xs font-medium text-stone-500">{LABELS[name] ?? name}</span>;
  if (typeof value === "string") {
    if (name === "kind") return <label className="block">{label}<p className="text-sm text-stone-600">{value}</p></label>;
    const rows = LONG.has(name) ? Math.min(18, Math.max(4, value.split("\n").length + 1)) : 1;
    return (
      <label className="block">
        {label}
        <textarea value={value} rows={rows} onChange={(e) => onChange(e.target.value)}
          className="block w-full resize-y rounded-lg border border-stone-200 px-2 py-1 text-sm " />
      </label>
    );
  }
  if (Array.isArray(value) && value.every((v) => typeof v === "string")) {
    return (
      <label className="block">
        {label}
        <textarea value={(value as string[]).join("\n")} rows={Math.max(2, value.length + 1)}
          onChange={(e) => onChange(e.target.value.split("\n"))}
          className="block w-full rounded-lg border border-stone-200 px-2 py-1 text-sm" />
      </label>
    );
  }
  if (Array.isArray(value)) {
    return (
      <div>
        {label}
        <div className="mt-1 space-y-2">
          {(value as Record<string, Value>[]).map((item, i) => (
            <div key={i} className="rounded-lg border border-stone-200 bg-stone-50 p-2">
              <FieldsEditor value={item} onChange={(v) => onChange((value as Record<string, Value>[]).map((x, j) => (j === i ? v : x)))} />
            </div>
          ))}
        </div>
      </div>
    );
  }
  return null;
}

/** Empty lines in list fields are dropped before saving. */
export function cleaned(content: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(content)) {
    if (Array.isArray(value)) {
      out[key] = value.every((v) => typeof v === "string")
        ? (value as string[]).map((v) => v.trim()).filter(Boolean)
        : (value as Record<string, unknown>[]).map(cleaned);
    } else out[key] = value;
  }
  return out;
}
