import type { Entity } from "../../api/types";
import { Quote } from "./bits";

/** Products, the company and customers, with their short forms and former names. */
export function NamesTab({ entities }: { entities: Entity[] }) {
  if (!entities.length) return <p className="p-6 text-sm text-stone-500">No names found yet.</p>;
  return (
    <table className="w-full text-left text-sm">
      <thead className="sticky top-0 bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
        <tr>
          <th className="px-6 py-2 font-medium">Name</th>
          <th className="px-2 py-2 font-medium">Kind</th>
          <th className="px-2 py-2 font-medium">Short forms</th>
          <th className="px-2 py-2 font-medium">Old names, and the proof</th>
        </tr>
      </thead>
      <tbody>
        {entities.map((entity) => (
          <tr key={entity.name} className="border-t border-stone-100 align-top">
            <td className="px-6 py-2 font-medium">{entity.name}</td>
            <td className="px-2 py-2 text-stone-600">{entity.kind}</td>
            <td className="px-2 py-2 text-stone-600">{entity.short_forms.join(", ") || "—"}</td>
            <td className="px-2 py-2 text-stone-600">
              {entity.old_names.length === 0 && "—"}
              {entity.old_names.map((old) => (
                <p key={old.name}>
                  <span className="font-medium">{old.name}</span>
                  <Quote text={old.evidence} />
                  <span className="ml-1 text-xs text-stone-400">({old.path})</span>
                </p>
              ))}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
