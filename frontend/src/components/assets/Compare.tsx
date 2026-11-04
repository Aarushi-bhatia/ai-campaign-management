/** Word-by-word difference between two versions: removed words struck out, added ones marked. */

type Piece = { kind: "same" | "added" | "removed"; text: string };

export function diffWords(before: string, after: string): Piece[] {
  const a = before.split(/(\s+)/);
  const b = after.split(/(\s+)/);
  const n = a.length;
  const m = b.length;
  if (n * m > 4_000_000) return [{ kind: "removed", text: before }, { kind: "added", text: after }];
  const table = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
  const pieces: Piece[] = [];
  const push = (kind: Piece["kind"], text: string) => {
    const last = pieces[pieces.length - 1];
    if (last && last.kind === kind) last.text += text;
    else pieces.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { push("same", a[i]); i++; j++; }
    else if (table[i + 1][j] >= table[i][j + 1]) push("removed", a[i++]);
    else push("added", b[j++]);
  }
  while (i < n) push("removed", a[i++]);
  while (j < m) push("added", b[j++]);
  return pieces;
}

export function Compare({ before, after }: { before: string; after: string }) {
  return (
    <pre className="whitespace-pre-wrap rounded-xl border border-stone-200 bg-white p-4 font-sans text-sm leading-relaxed shadow-sm">
      {diffWords(before, after).map((piece, i) =>
        piece.kind === "same" ? <span key={i}>{piece.text}</span>
          : piece.kind === "added" ? <ins key={i} className="bg-emerald-100 text-emerald-900 no-underline">{piece.text}</ins>
          : <del key={i} className="bg-red-100 text-red-800">{piece.text}</del>,
      )}
    </pre>
  );
}
