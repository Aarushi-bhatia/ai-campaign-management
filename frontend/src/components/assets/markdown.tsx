/** Just enough markdown for blog bodies and section text: headings, lists, bold, italics and links. */

function inline(text: string, key: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const token = match[0];
    const k = `${key}-${n++}`;
    if (token.startsWith("**")) parts.push(<strong key={k}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) parts.push(<code key={k} className="rounded bg-stone-100 px-1 text-[0.9em]">{token.slice(1, -1)}</code>);
    else if (token.startsWith("[")) {
      const [, label, href] = token.match(/\[([^\]]+)\]\(([^)]+)\)/)!;
      parts.push(<a key={k} href={href} target="_blank" rel="noreferrer" className="text-sky-700 underline">{label}</a>);
    } else parts.push(<em key={k}>{token.slice(1, -1)}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const blocks = text.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className={`space-y-3 ${className}`}>
      {blocks.map((block, i) => {
        const key = String(i);
        const heading = block.match(/^(#{1,4})\s+(.*)$/);
        if (heading && !block.includes("\n")) {
          const size = heading[1].length <= 2 ? "text-xl" : "text-lg";
          return <h3 key={key} className={`${size} mt-5 font-semibold`}>{inline(heading[2], key)}</h3>;
        }
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const items = lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""), `${key}-${j}`)}</li>);
          return ordered ? <ol key={key} className="list-decimal space-y-1 pl-5">{items}</ol>
            : <ul key={key} className="list-disc space-y-1 pl-5">{items}</ul>;
        }
        if (block.startsWith(">")) {
          return <blockquote key={key} className="border-l-4 border-stone-300 pl-3 italic text-stone-600">{inline(block.replace(/^>\s?/gm, ""), key)}</blockquote>;
        }
        return <p key={key} className="whitespace-pre-line">{inline(block, key)}</p>;
      })}
    </div>
  );
}
