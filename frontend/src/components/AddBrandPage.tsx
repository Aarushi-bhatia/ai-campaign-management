import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type PickedFile } from "../api/client";

type Props = {
  /** When set, the chosen files update this brand instead of creating a new one. */
  updating?: { id: number; name: string };
  onAdded: (brandId: number) => void;
};

/** Pick a brand folder, leave out folders that aren't brand material (such as briefs), and upload it. */
export function AddBrandPage({ updating, onAdded }: Props) {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<PickedFile[]>([]);
  const [name, setName] = useState("");
  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  const upload = useMutation({
    mutationFn: () =>
      updating ? api.updateBrand(updating.id, picked, [...excluded]) : api.addBrand(name, picked, [...excluded]),
    onSuccess: (brand) => {
      queryClient.invalidateQueries({ queryKey: ["brands"] });
      queryClient.invalidateQueries({ queryKey: ["brand", brand.id] });
      onAdded(brand.id);
    },
  });

  function pick(fileList: FileList | null) {
    const files = [...(fileList ?? [])]
      .map((file) => ({ path: file.webkitRelativePath || file.name, file }))
      .filter(({ path }) => !path.split("/").some((part) => part.startsWith(".")));
    setPicked(files);
    setName(files[0]?.path.split("/")[0] ?? "");
    setExcluded(new Set());
  }

  const folders = topFolders(picked);

  return (
    <section className="flex min-w-0 flex-1 justify-center overflow-y-auto bg-white p-8">
      <div className="w-full max-w-xl">
        <h1 className="text-xl font-medium">{updating ? `Update ${updating.name}` : "Add a brand"}</h1>
        <p className="mt-1 text-sm text-stone-500">
          {updating
            ? "Choose the whole brand folder again. New and changed files are read; unchanged files keep their work, and your corrections stay."
            : "Choose the brand's folder. The app reads every text document in it once, notes what each one is, and keeps the images for later."}
        </p>

        <label className="mt-6 block rounded-xl border-2 border-dashed border-stone-200 p-6 text-center text-sm text-stone-600 hover:border-stone-400">
          <input
            type="file"
            className="hidden"
            // @ts-expect-error: folder picking is a non-standard attribute that browsers support
            webkitdirectory=""
            multiple
            onChange={(event) => pick(event.target.files)}
          />
          {picked.length ? `${picked.length} files chosen. Choose again` : "Choose a folder"}
        </label>

        {picked.length > 0 && (
          <>
            {!updating && (
              <label className="mt-6 block text-sm font-medium">
                Brand name
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-1 block w-full rounded-lg border border-stone-200 px-3 py-2 font-normal"
                />
              </label>
            )}

            {folders.length > 0 && (
              <fieldset className="mt-6">
                <legend className="text-sm font-medium">Folders to read</legend>
                <p className="text-xs text-stone-500">
                  Untick anything that isn't brand material, such as campaign briefs.
                </p>
                <div className="mt-2 space-y-1">
                  {folders.map(({ folder, count }) => (
                    <label key={folder} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={!excluded.has(folder)}
                        onChange={() => setExcluded(toggle(excluded, folder))}
                      />
                      <span>{folder}/</span>
                      <span className="text-stone-400">{count} files</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}

            <button
              onClick={() => upload.mutate()}
              disabled={upload.isPending || (!updating && !name.trim())}
              className="mt-6 rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-800 disabled:opacity-40"
            >
              {upload.isPending ? "Uploading…" : updating ? "Update brand" : "Add brand"}
            </button>
            {upload.isError && <p className="mt-2 text-sm text-red-600">{upload.error.message}</p>}
          </>
        )}
      </div>
    </section>
  );
}

/** Folders just inside the chosen folder, with how many files each holds. */
function topFolders(files: PickedFile[]): { folder: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const { path } of files) {
    const parts = path.split("/");
    if (parts.length > 2) counts.set(parts[1], (counts.get(parts[1]) ?? 0) + 1);
  }
  return [...counts].sort(([a], [b]) => a.localeCompare(b)).map(([folder, count]) => ({ folder, count }));
}

function toggle(set: Set<string>, value: string): Set<string> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}
