import type { Asset } from "../../api/types";
import { Markdown } from "./markdown";

/** Each asset type drawn the way a reader would meet it. */
export function Preview({ asset, brandName }: { asset: Asset; brandName: string }) {
  const c = asset.content ?? {};
  switch (asset.type) {
    case "email":
      return <EmailPreview c={c} asset={asset} />;
    case "linkedin_post":
      return <LinkedInPreview c={c} asset={asset} brandName={brandName} />;
    case "x_post":
      return <XPreview c={c} asset={asset} brandName={brandName} />;
    case "blog_post":
      return <BlogPreview c={c} asset={asset} />;
    case "landing_page":
      return <LandingPreview c={c} asset={asset} brandName={brandName} />;
  }
}

type P = { c: Record<string, any>; asset: Asset };

function Picture({ asset, className }: { asset: Asset; className: string }) {
  if (asset.image_url) return <img src={asset.image_url} alt={asset.image?.alt_text ?? ""} className={className} />;
  if (asset.image?.suggestion) {
    return (
      <div className={`flex items-center justify-center border border-dashed border-stone-300 bg-stone-50 p-4 text-center text-xs text-stone-500 ${className}`}>
        No suitable image. {asset.image.suggestion}
      </div>
    );
  }
  return null;
}

function Avatar({ name, round = true }: { name: string; round?: boolean }) {
  return (
    <div className={`flex h-10 w-10 shrink-0 items-center justify-center bg-stone-800 text-sm font-semibold text-white ${round ? "rounded-full" : "rounded"}`}>
      {(name || "?").slice(0, 1).toUpperCase()}
    </div>
  );
}

/** A date to show: the plan's placeholder ("to be set") and empty values are not dates. */
function realDate(date: string | undefined): boolean {
  return Boolean(date && date.trim() && !/to be set|tbd|tbc/i.test(date));
}

function tag(t: string) {
  return t.startsWith("#") ? t : `#${t}`;
}

function EmailPreview({ c, asset }: P) {
  const sender: string = c.sender ?? "";
  return (
    <div className="overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
      <div className="border-b border-stone-200 bg-stone-50 px-4 py-2 text-xs text-stone-500">Inbox</div>
      <div className="flex gap-3 border-b border-stone-100 bg-sky-50/60 px-4 py-3">
        <Avatar name={sender} />
        <div className="min-w-0">
          <p className="text-sm font-semibold">{sender}</p>
          <p className="truncate text-sm"><span className="font-medium">{c.subject}</span> <span className="text-stone-500">— {c.preview_text}</span></p>
        </div>
      </div>
      <div className="px-4 py-4">
        <p className="text-lg font-semibold">{c.subject}</p>
        <p className="mb-4 text-xs text-stone-500">From {sender}</p>
        <div className="mx-auto max-w-[560px] space-y-4 text-[15px] leading-relaxed">
          <Picture asset={asset} className="w-full rounded" />
          {(c.sections ?? []).map((s: { heading: string; body: string }, i: number) => (
            <section key={i}>
              {s.heading && <h3 className="mb-1 font-semibold">{s.heading}</h3>}
              <Markdown text={s.body} />
            </section>
          ))}
          {c.button_text && (
            <a href={c.button_link || "#"} target="_blank" rel="noreferrer" className="inline-block rounded-md bg-stone-900 px-5 py-2.5 text-sm font-medium text-white">
              {c.button_text}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function LinkedInPreview({ c, asset, brandName }: P & { brandName: string }) {
  const author = c.author || brandName;
  return (
    <div className="mx-auto max-w-[555px] rounded-lg border border-stone-300 bg-white shadow-sm">
      <div className="flex gap-2 px-4 pt-3">
        <Avatar name={author} round={false} />
        <div>
          <p className="text-sm font-semibold">{author}</p>
          <p className="text-xs text-stone-500">1d · 🌐</p>
        </div>
      </div>
      <p className="whitespace-pre-line px-4 py-2 text-sm leading-relaxed">{c.text}</p>
      {(c.hashtags ?? []).length > 0 && (
        <p className="px-4 pb-2 text-sm font-medium text-sky-700">{c.hashtags.map(tag).join(" ")}</p>
      )}
      <Picture asset={asset} className="w-full" />
      <div className="flex justify-around border-t border-stone-200 px-2 py-2 text-xs font-medium text-stone-500">
        <span>👍 Like</span><span>💬 Comment</span><span>🔁 Repost</span><span>➤ Send</span>
      </div>
    </div>
  );
}

function XPreview({ c, asset, brandName }: P & { brandName: string }) {
  const author = c.author || brandName;
  const handle = `@${author.replace(/[^A-Za-z0-9_]/g, "").slice(0, 15) || "brand"}`;
  // X counts every link as 23 characters, however long it is.
  const full = [c.text, (c.hashtags ?? []).map(tag).join(" ")].filter(Boolean).join(" ")
    .replace(/https?:\/\/[^\s)\]>"'`]+/g, "x".repeat(23));
  return (
    <div className="mx-auto max-w-[598px] rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex gap-3">
        <Avatar name={author} />
        <div className="min-w-0 flex-1">
          <p className="text-[15px]"><span className="font-bold">{author}</span> <span className="text-stone-500">{handle} · 1h</span></p>
          <p className="mt-0.5 whitespace-pre-line text-[15px] leading-snug">
            {c.text}
            {(c.hashtags ?? []).length > 0 && <span className="text-sky-600"> {c.hashtags.map(tag).join(" ")}</span>}
          </p>
          <Picture asset={asset} className="mt-3 w-full rounded-2xl border border-stone-200" />
          <div className="mt-3 flex justify-between pr-8 text-xs text-stone-500">
            <span>💬 12</span><span>🔁 34</span><span>♡ 210</span><span className={full.length > 280 ? "font-semibold text-red-600" : ""}>{full.length}/280</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function BlogPreview({ c, asset }: P) {
  return (
    <article className="rounded-lg border border-stone-200 bg-white px-8 py-8 shadow-sm">
      <p className="text-xs uppercase tracking-widest text-stone-400">Blog</p>
      <h1 className="mt-2 text-3xl font-bold leading-tight">{c.title}</h1>
      <p className="mt-2 text-sm text-stone-500">{c.author}{realDate(c.date) && ` · ${c.date}`}</p>
      <Picture asset={asset} className="mt-5 w-full rounded" />
      <Markdown text={c.body ?? ""} className="mt-6 text-[16px] leading-7" />
    </article>
  );
}

type Section = {
  kind: string; heading: string; body: string; items: string[]; button_text: string;
  button_link?: string; link_text?: string; link_url?: string;
};

/** The section's quieter second link, such as the docs, beside its main button. */
function SecondLink({ s, dark }: { s: Section; dark?: boolean }) {
  if (!s.link_text) return null;
  return (
    <a href={s.link_url || "#"} target="_blank" rel="noreferrer"
      className={`ml-4 mt-6 inline-block text-sm font-medium underline ${dark ? "text-stone-200" : "text-stone-700"}`}>
      {s.link_text} →
    </a>
  );
}

function LandingPreview({ c, asset, brandName }: P & { brandName: string }) {
  const sections: Section[] = c.sections ?? [];
  return (
    <div className="overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-stone-200 px-5 py-3 text-sm">
        <span className="font-bold">{brandName}</span>
        <span className="text-xs text-stone-400">Product · Customers · Pricing</span>
      </div>
      {sections[0]?.kind !== "hero" && <Picture asset={asset} className="w-full" />}
      {sections.map((s, i) => <LandingSection key={i} s={s} asset={asset} first={i === 0} />)}
    </div>
  );
}

function LandingSection({ s, asset, first }: { s: Section; asset: Asset; first: boolean }) {
  if (s.kind === "hero") {
    return (
      <section className="bg-stone-900 px-8 py-12 text-white">
        <h1 className="max-w-xl text-3xl font-bold leading-tight">{s.heading}</h1>
        <Markdown text={s.body} className="mt-3 max-w-xl text-stone-300" />
        {s.button_text && <span className="mt-6 inline-block rounded-md bg-white px-5 py-2.5 text-sm font-semibold text-stone-900">{s.button_text}</span>}
        <SecondLink s={s} dark />
        {first && <Picture asset={asset} className="mt-8 w-full rounded-lg" />}
      </section>
    );
  }
  if (s.kind === "cta") {
    return (
      <section className="bg-stone-100 px-8 py-10 text-center">
        <h2 className="text-2xl font-bold">{s.heading}</h2>
        <Markdown text={s.body} className="mx-auto mt-2 max-w-lg text-stone-600" />
        {s.button_text && <span className="mt-5 inline-block rounded-md bg-stone-900 px-5 py-2.5 text-sm font-semibold text-white">{s.button_text}</span>}
        <SecondLink s={s} />
      </section>
    );
  }
  const grid = s.kind === "features" || s.kind === "how_it_works" || s.kind === "proof";
  return (
    <section className="border-b border-stone-100 px-8 py-10">
      {s.heading && <h2 className="text-xl font-bold">{s.heading}</h2>}
      {s.body && <Markdown text={s.body} className="mt-2 text-stone-700" />}
      {s.items.length > 0 && (
        grid ? (
          <div className="mt-5 grid grid-cols-2 gap-4">
            {s.items.map((item, i) => (
              <div key={i} className={`rounded-lg border border-stone-200 p-4 text-sm ${s.kind === "proof" ? "italic text-stone-700" : ""}`}>
                {s.kind === "how_it_works" && <span className="mr-2 font-bold text-stone-400">{i + 1}</span>}
                <Markdown text={item} />
              </div>
            ))}
          </div>
        ) : (
          <ul className="mt-4 space-y-2 text-sm">
            {s.items.map((item, i) => <li key={i} className="border-b border-stone-100 pb-2"><Markdown text={item} /></li>)}
          </ul>
        )
      )}
      {s.button_text && <span className="mt-5 inline-block rounded-md border border-stone-900 px-4 py-2 text-sm font-medium">{s.button_text}</span>}
      <SecondLink s={s} />
    </section>
  );
}

/** The asset as plain text, for the Copy button. */
export function copyText(asset: Asset): string {
  const c = asset.content ?? {};
  const tags = (c.hashtags ?? []).map(tag).join(" ");
  switch (asset.type) {
    case "email":
      return [`From: ${c.sender}`, `Subject: ${c.subject}`, `Preview: ${c.preview_text}`, "",
        ...(c.sections ?? []).flatMap((s: { heading: string; body: string }) => [s.heading, s.body, ""].filter((x, i) => i > 0 || x)),
        ...(c.button_text ? [`[${c.button_text}](${c.button_link || "#"})`] : [])].join("\n");
    case "linkedin_post":
    case "x_post":
      return [c.text, tags].filter(Boolean).join("\n\n");
    case "blog_post":
      return `# ${c.title}\n\n${c.author}${realDate(c.date) ? ` · ${c.date}` : ""}\n\n${c.body}`;
    case "landing_page":
      return (c.sections ?? []).map((s: Section) =>
        [`## ${s.heading}`, s.body, ...s.items.map((i) => `- ${i}`),
          s.button_text && (s.button_link ? `[${s.button_text}](${s.button_link})` : `[${s.button_text}]`),
          s.link_text && `[${s.link_text}](${s.link_url || "#"})`].filter(Boolean).join("\n"),
      ).join("\n\n");
  }
}
