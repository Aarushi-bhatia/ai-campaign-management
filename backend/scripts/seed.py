"""A brand already read, saved to one file, so a new install can skip reading the sample brand. It is not part of
the app: Docker runs it as its own step, before the app starts, only when asked.

    docker compose --profile seed up                                                 # load the sample brand
    docker compose exec backend uv run python -m scripts.seed export 2 seed/wickhold.tar.gz   # save a brand

`export` writes one brand's rows, the AI calls that read it (so the Brand page's View prompt and the reading cost
still work) and its stored files into one .tar.gz. `load` puts them into a database with no brand yet. Chats,
memory and campaigns are never part of it.

Rows keep their ids, so every link between them holds; that is why a seed only loads into a database with no
brand. It also loads only into the schema it was taken from: after a migration, export it again.
"""

import io
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.brand.files import storage_path
from app.config import get_settings

TABLES = ("brands", "ai_calls", "brand_files", "entities", "doc_links", "facts", "conflicts", "brand_decisions",
          "sections", "image_info")
"""In loading order: a row only points at rows loaded before it, except the brand's own AI calls (see below)."""

BRAND_CALLS = ("summary_call_id", "image_rules_call_id", "writing_rules_call_id")
"""The brand points at AI calls that point back at it, so these are set once the calls are in."""

_CALL_REFS = {"brand_files": ("card_call_id", "facts_call_id"), "conflicts": ("call_id",),
              "image_info": ("describe_call_id", "notes_call_id")}


class SeedError(Exception):
    """The seed can't be loaded into this database."""


class HasBrand(SeedError):
    """The database has a brand already, so the seed is left out; the app works as it is."""


def export(database_url: str, data_dir: Path, brand_id: int, out: Path) -> dict[str, int]:
    """Writes the brand to `out`, and says how many rows of each table went in."""
    counts: dict[str, int] = {}
    with _connect(database_url) as conn, tarfile.open(out, "w:gz") as tar:
        manifest = {"revision": _revision(conn), "brand_id": brand_id, "columns": {}}
        for table in TABLES:
            columns = _columns(conn, table)
            manifest["columns"][table] = columns
            data, counts[table] = _copy_out(conn, table, columns, brand_id)
            _add(tar, f"tables/{table}.csv", data)
        manifest["brand_calls"] = dict(zip(BRAND_CALLS, conn.execute(
            sql.SQL("SELECT {} FROM brands WHERE id = %s").format(sql.SQL(", ").join(map(sql.Identifier, BRAND_CALLS))),
            (brand_id,)).fetchone() or (None,) * len(BRAND_CALLS), strict=True))
        _add(tar, "manifest.json", json.dumps(manifest, indent=1).encode())
        folder = storage_path(data_dir, brand_id, "")
        for file in sorted(p for p in folder.rglob("*") if p.is_file()):
            tar.add(file, arcname=f"files/{file.relative_to(folder).as_posix()}")
    return counts


def load(database_url: str, data_dir: Path, seed: Path) -> int:
    """Loads the seed into a database with no brand yet, and returns the brand's id."""
    with tarfile.open(seed, "r:gz") as tar, _connect(database_url) as conn:
        manifest = json.loads(_read(tar, "manifest.json"))
        if conn.execute("SELECT 1 FROM brands LIMIT 1").fetchone():
            raise HasBrand("there is a brand already")
        if manifest["revision"] != _revision(conn):
            raise SeedError(f"it was made for database version {manifest['revision']}, not {_revision(conn)}")
        brand_id = manifest["brand_id"]
        with conn.transaction():
            for table in TABLES:
                columns, data = manifest["columns"][table], _read(tar, f"tables/{table}.csv")
                if table == "brands":
                    _load_brand(conn, columns, data)
                else:
                    _copy_in(conn, table, columns, data)
            calls = manifest["brand_calls"]
            # Unreviewed, so the Brand page opens once by itself and shows what was read, as after a real read.
            conn.execute(sql.SQL("UPDATE brands SET {}, reviewed = false WHERE id = %s").format(
                sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in calls)),
                (*calls.values(), brand_id))
            for table in TABLES:
                conn.execute(sql.SQL("SELECT setval(pg_get_serial_sequence({}, 'id'), "
                                     "coalesce((SELECT max(id) FROM {}), 1))").format(
                    sql.Literal(table), sql.Identifier(table)))
            _unpack_files(tar, storage_path(data_dir, brand_id, ""))
    return brand_id


def _copy_out(conn: psycopg.Connection, table: str, columns: list[str], brand_id: int) -> tuple[bytes, int]:
    """The brand's rows, and how many. Its AI calls are the brand-wide ones (no chat) and any its rows point at;
    a call made in a chat is kept without the chat, which isn't exported."""
    brand = sql.Literal(brand_id)
    selected = [sql.SQL("NULL") if (table, c) == ("ai_calls", "chat_id") else sql.Identifier(c) for c in columns]
    if table == "brands":
        where = sql.SQL("id = {}").format(brand)
    elif table == "ai_calls":
        refs = [sql.SQL("SELECT {} FROM {} WHERE brand_id = {}").format(sql.Identifier(c), sql.Identifier(t), brand)
                for t, cs in _CALL_REFS.items() for c in cs]
        refs += [sql.SQL("SELECT {} FROM brands WHERE id = {}").format(sql.Identifier(c), brand) for c in BRAND_CALLS]
        where = sql.SQL("(brand_id = {} AND chat_id IS NULL) OR id IN ({})").format(
            brand, sql.SQL(" UNION ").join(refs))
    else:
        where = sql.SQL("brand_id = {}").format(brand)
    query = sql.SQL("COPY (SELECT {} FROM {} WHERE {} ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER)").format(
        sql.SQL(", ").join(selected), sql.Identifier(table), where)
    out, cursor = io.BytesIO(), conn.cursor()
    with cursor.copy(query) as copy:
        for chunk in copy:
            out.write(chunk)
    return out.getvalue(), cursor.rowcount


def _copy_in(conn: psycopg.Connection, table: str, columns: list[str], data: bytes) -> None:
    query = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER)").format(
        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns)))
    with conn.cursor().copy(query) as copy:
        copy.write(data)


def _load_brand(conn: psycopg.Connection, columns: list[str], data: bytes) -> None:
    """The brand row, without its AI calls for now: they point back at the brand, so they aren't in yet. It goes
    through a copy of the table, so the CSV is loaded as written (rewriting it would lose "" against NULL)."""
    conn.execute("CREATE TEMP TABLE seed_brands (LIKE brands) ON COMMIT DROP")
    _copy_in(conn, "seed_brands", columns, data)
    conn.execute(sql.SQL("UPDATE seed_brands SET {}").format(
        sql.SQL(", ").join(sql.SQL("{} = NULL").format(sql.Identifier(c)) for c in BRAND_CALLS)))
    conn.execute("INSERT INTO brands SELECT * FROM seed_brands")


def _unpack_files(tar: tarfile.TarFile, folder: Path) -> None:
    members = []
    for member in tar.getmembers():
        path = PurePosixPath(member.name)
        if member.isfile() and path.parts[0] == "files" and len(path.parts) > 1:
            member.name = PurePosixPath(*path.parts[1:]).as_posix()
            members.append(member)
    folder.mkdir(parents=True, exist_ok=True)
    tar.extractall(folder, members=members, filter="data")  # "data" refuses absolute paths and ".."


def _columns(conn: psycopg.Connection, table: str) -> list[str]:
    rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s "
                        "AND table_schema = current_schema() ORDER BY ordinal_position", (table,)).fetchall()
    return [name for (name,) in rows]


def _revision(conn: psycopg.Connection) -> str:
    row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return row[0] if row else ""


def _connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False))


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _read(tar: tarfile.TarFile, name: str) -> bytes:
    member = tar.extractfile(name)
    if member is None:
        raise SeedError(f"{name} is missing from the seed")
    return member.read()


def main(args: list[str]) -> int:
    settings = get_settings()
    if len(args) == 3 and args[0] == "export":
        out = Path(args[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        for table, rows in export(settings.database_url, settings.data_dir, int(args[1]), out).items():
            print(f"{table}: {rows}")
        print(f"Wrote {out} ({out.stat().st_size / 1_000_000:.1f} MB)")
        return 0
    if len(args) == 2 and args[0] == "load":
        try:
            brand_id = load(settings.database_url, settings.data_dir, Path(args[1]))
        except HasBrand:
            print("Seed not loaded: the app has a brand already.")
            return 0
        except SeedError as error:
            print(f"Seed not loaded: {error}.", file=sys.stderr)
            return 1
        print(f"Loaded the seed brand from {args[1]} as brand {brand_id}.")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
