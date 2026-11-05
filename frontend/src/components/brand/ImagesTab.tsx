import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { AssetChannel, Brand, BrandImage, ImageRules } from "../../api/types";
import { Line } from "./bits";
import type { Corrections } from "./useCorrections";

const CHANNELS: [AssetChannel, string][] = [
  ["email", "Email"],
  ["linkedin", "LinkedIn"],
  ["x", "X"],
  ["blog", "Blog"],
  ["landing_page", "Landing page"],
];

type Filter = "all" | "usable" | "blocked";

type Props = {
  brand: Brand;
  corrections: Corrections;
  onViewPrompt: (callId: number) => void;
};

/** The image library: what may be used where, and why not. */
export function ImagesTab({ brand, corrections, onViewPrompt }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [openPath, setOpenPath] = useState<string | null>(null);
  const shown = brand.images.filter(
    (image) => filter === "all" || (filter === "usable" ? !image.blocked : Boolean(image.blocked)),
  );
  const open = brand.images.find((image) => image.path === openPath);
  const blockedCount = brand.images.filter((image) => image.blocked).length;

  useEffect(() => {
    if (!openPath) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setOpenPath(null);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [openPath]);

  return (
    <div className="space-y-4 p-6">
      {brand.image_rules && (
        <ChannelRules rules={brand.image_rules} callId={brand.image_rules_call_id} onViewPrompt={onViewPrompt} />
      )}
      <TryPicking brandId={brand.id} onViewPrompt={onViewPrompt} />
      <div className="flex items-center gap-3 text-sm">
        {(["all", "usable", "blocked"] as Filter[]).map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`rounded-full px-3 py-1 ${filter === value ? "bg-brand-soft font-medium text-violet-900" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}
          >
            {value === "all" ? `All (${brand.images.length})` : value === "usable" ? `Usable (${brand.images.length - blockedCount})` : `Blocked (${blockedCount})`}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        {shown.map((image) => (
          <button
            key={image.path}
            onClick={() => setOpenPath(image.path === openPath ? null : image.path)}
            className={`overflow-hidden rounded-lg border text-left ${image.path === openPath ? "border-violet-700" : "border-stone-200 hover:border-stone-400"}`}
          >
            <div className="flex h-24 items-center justify-center bg-[repeating-conic-gradient(#eee_0_25%,#fff_0_50%)] bg-[length:16px_16px]">
              <img src={image.url} alt={image.description} loading="lazy" className={`max-h-24 max-w-full ${image.blocked ? "opacity-40" : ""}`} />
            </div>
            <div className="p-2 text-xs">
              <p className="truncate font-medium">{image.title || image.path.split("/").pop()}</p>
              <p className={`truncate ${image.blocked ? "text-red-700" : "text-stone-500"}`}>
                {image.blocked ?? image.image_type.replace("_", " ")}
              </p>
            </div>
          </button>
        ))}
      </div>
      {open && <ImageDetail image={open} corrections={corrections} onViewPrompt={onViewPrompt} onClose={() => setOpenPath(null)} />}
    </div>
  );
}

function ImageDetail({ image, corrections, onViewPrompt, onClose }: { image: BrandImage; onClose: () => void } & Omit<Props, "brand">) {
  const fix = corrections.decisionFor("image_usable", image.path);
  const notes = image.notes;
  return (
    <section className="sticky bottom-0 space-y-2 rounded-xl border border-stone-200 bg-white p-4 text-sm shadow-lg">
      <div className="flex gap-4">
        <img src={image.url} alt={image.description} className="h-28 rounded-lg border border-stone-200 object-contain" />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium">{image.path}</p>
          <p className="text-stone-700">{image.description || "No description."}</p>
          <p className="text-xs text-stone-400">
            {image.image_type.replace("_", " ") || "type unknown"} · {image.width}×{image.height}
            {image.transparent && " · see-through"} · description from{" "}
            {{ file: "the image info file", ai: "the vision model", name: "the file name", "": "nowhere yet" }[image.description_source]}
          </p>
        </div>
        <button onClick={onClose} title="Close (Esc)" aria-label="Close" className="self-start text-lg leading-none text-stone-400 hover:text-stone-700">
          ✕
        </button>
      </div>
      <Line label="Status">
        {image.blocked ? <span className="text-red-700">Blocked: {image.blocked}</span> : <span className="text-emerald-700">Usable</span>}
      </Line>
      {notes && notes.rules.length > 0 && <Line label="Conditions">{notes.rules.join("; ")}</Line>}
      <Line label="By channel">
        {CHANNELS.map(([channel, label]) => (
          <span key={channel} className={`mr-3 ${image.channels[channel] ? "text-red-700" : "text-emerald-700"}`} title={image.channels[channel] ?? "Can be used"}>
            {image.channels[channel] ? "✕" : "✓"} {label}
          </span>
        ))}
      </Line>
      {typeof image.record.restrictions === "string" && image.record.restrictions && (
        <Line label="Its notes">{String(image.record.restrictions)}</Line>
      )}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="min-w-28 font-medium uppercase tracking-wide text-stone-400">Correct</span>
        <button disabled={corrections.busy} onClick={() => corrections.correct("image_usable", image.path, "yes")} className="underline text-violet-700">
          Mark usable
        </button>
        <button disabled={corrections.busy} onClick={() => corrections.correct("image_usable", image.path, "no")} className="underline text-violet-700">
          Mark not usable
        </button>
        {fix && (
          <button onClick={() => corrections.undo(fix)} className="underline text-violet-700">
            Undo (you marked it {fix.value === "yes" ? "usable" : "not usable"})
          </button>
        )}
        {image.describe_call_id && (
          <button onClick={() => onViewPrompt(image.describe_call_id!)} className="underline text-stone-500">View description prompt</button>
        )}
        {image.notes_call_id && (
          <button onClick={() => onViewPrompt(image.notes_call_id!)} className="underline text-stone-500">View restrictions prompt</button>
        )}
      </div>
    </section>
  );
}

function ChannelRules({ rules, callId, onViewPrompt }: { rules: ImageRules; callId: number | null; onViewPrompt: (id: number) => void }) {
  return (
    <details className="rounded-xl border border-stone-200 p-3 text-sm">
      <summary className="cursor-pointer font-medium">Image rules per channel, from the brand's documents</summary>
      <div className="mt-2 space-y-2">
        {CHANNELS.map(([channel, label]) => {
          const rule = rules.channels[channel];
          const fixed = [
            rule.block_transparent && "no see-through images",
            rule.orientation !== "any" && `${rule.orientation} only`,
            rule.allowed_types.length > 0 && `only ${rule.allowed_types.join(", ")}`,
            rule.blocked_types.length > 0 && `never ${rule.blocked_types.join(", ")}`,
            rule.min_width > 0 && `at least ${rule.min_width}px wide`,
            rule.image_optional && "image often better left out",
          ].filter(Boolean);
          return (
            <Line key={channel} label={label}>
              {fixed.length ? <span className="font-medium">{fixed.join(" · ")}</span> : <span className="text-stone-400">no fixed limits</span>}
              {rule.notes.length > 0 && <span className="ml-2 text-stone-600">{rule.notes.join(" ")}</span>}
            </Line>
          );
        })}
        {rules.alt_text_rules.length > 0 && <Line label="Alt text">{rules.alt_text_rules.join(" ")}</Line>}
        {callId && (
          <button onClick={() => onViewPrompt(callId)} className="text-xs text-stone-500 underline">View prompt</button>
        )}
      </div>
    </details>
  );
}

/** Tries the picker on the real library, the same way a campaign asset will use it. */
function TryPicking({ brandId, onViewPrompt }: { brandId: number; onViewPrompt: (id: number) => void }) {
  const [channel, setChannel] = useState<AssetChannel>("email");
  const [message, setMessage] = useState("");
  const pick = useMutation({
    mutationFn: () => api.pickImages(brandId, { channel, asset_type: `${channel} asset`, message }),
  });
  return (
    <details className="rounded-xl border border-stone-200 p-3 text-sm">
      <summary className="cursor-pointer font-medium">Try picking images for an asset</summary>
      <div className="mt-2 flex gap-2">
        <select value={channel} onChange={(event) => setChannel(event.target.value as AssetChannel)} className="rounded-lg border border-stone-200 px-2">
          {CHANNELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="What the asset says, e.g. Our new release contains a failing pod in seconds"
          className="flex-1 rounded-lg border border-stone-200 px-2 py-1"
        />
        <button onClick={() => pick.mutate()} disabled={!message.trim() || pick.isPending} className="rounded-lg bg-violet-700 px-3 text-white disabled:opacity-40">
          {pick.isPending ? "Picking…" : "Pick"}
        </button>
      </div>
      {pick.error && <p className="mt-2 text-red-600">{pick.error.message}</p>}
      {pick.data && (
        <div className="mt-3 space-y-2">
          {pick.data.choices.map((choice) => (
            <div key={choice.path} className="flex gap-3">
              <img src={choice.url} alt={choice.alt_text} className="h-16 rounded-lg border border-stone-200" />
              <div>
                <p className="font-medium">{choice.path}</p>
                <p className="text-stone-600">{choice.why}</p>
                <p className="text-xs text-stone-500">Alt text: {choice.alt_text}</p>
              </div>
            </div>
          ))}
          {pick.data.suggestion && <p className="text-amber-800">Nothing fits: {pick.data.suggestion}</p>}
          <p className="text-xs text-stone-500">
            {pick.data.blocked.length} images were blocked before ranking.
            {pick.data.call_id && (
              <button onClick={() => onViewPrompt(pick.data!.call_id!)} className="ml-2 underline">View prompt</button>
            )}
          </p>
          {pick.data.blocked.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-stone-500 underline">Show the {pick.data.blocked.length} blocked images and why</summary>
              <ul className="mt-2 space-y-1">
                {pick.data.blocked.map((b) => (
                  <li key={b.path}>
                    <span className="font-medium">{b.path.split("/").pop()}</span>
                    <span className="text-red-700">: {b.reason}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </details>
  );
}
