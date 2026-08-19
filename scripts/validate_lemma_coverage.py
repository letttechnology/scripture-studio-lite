#!/usr/bin/env python3
"""
validate_lemma_coverage.py

Validates our lexeme table coverage against James Tauber's greek-lemma-mappings
and optionally populates gk_number on the lexeme table.

Reference: https://github.com/jtauber/greek-lemma-mappings

Reports:
  1. Gap lemmas (no strongs in Tauber) — how we handle them
  2. Strong's mismatches between Tauber and our lexeme.strongs_id
  3. Lemmas in Tauber completely absent from our lexeme table
  4. GK number coverage (how many we can populate)

Usage:
  python scripts/validate_lemma_coverage.py              # report only
  python scripts/validate_lemma_coverage.py --populate-gk  # report + write gk_number to DB
  python scripts/validate_lemma_coverage.py --export data/tauber-gk-mapping.json
"""

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path

import psycopg2
import requests
import yaml

# ---------------------------------------------------------------------------
TAUBER_URL = "https://raw.githubusercontent.com/jtauber/greek-lemma-mappings/master/lexemes.yaml"
CACHE_FILE = Path("data/tauber-lexemes-cache.yaml")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "interlinear_bible_dev")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", os.getenv("DB_PASSWORD", "letttech"))
# ---------------------------------------------------------------------------


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s) if s else s


def load_tauber(force_refresh: bool = False) -> dict:
    if CACHE_FILE.exists() and not force_refresh:
        print(f"[Tauber] Using cached data from {CACHE_FILE}")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    print(f"[Tauber] Downloading from {TAUBER_URL} ...")
    resp = requests.get(TAUBER_URL, timeout=30)
    resp.raise_for_status()
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(resp.text, encoding="utf-8")
    print(f"[Tauber] Cached to {CACHE_FILE}")
    return yaml.safe_load(resp.text)


def load_our_lexemes(conn) -> tuple[dict, dict]:
    """Returns (by_nfc_lemma, by_strongs_id) dicts."""
    cur = conn.cursor()
    cur.execute("SELECT id, strongs_id, lemma, gk_number FROM lexeme")
    by_lemma = {}
    by_strongs = {}
    for row_id, strongs_id, lemma, gk_number in cur.fetchall():
        entry = {"id": row_id, "strongs_id": strongs_id, "gk_number": gk_number, "lemma": lemma}
        if lemma:
            by_lemma[nfc(lemma)] = entry
        if strongs_id:
            by_strongs[strongs_id] = entry
    return by_lemma, by_strongs


def strongs_fmt(raw) -> str | None:
    """Normalize Tauber strongs value (int or str) to 'G####' format."""
    if raw is None:
        return None
    s = str(raw).strip()
    if s.isdigit():
        return f"G{int(s)}"
    if s.upper().startswith("G"):
        return s.upper()
    return s


def gk_fmt(raw) -> str | None:
    """Normalize Tauber gk value to string, handling lists."""
    if raw is None:
        return None
    if isinstance(raw, list):
        # take first GK number when there are multiple
        return str(raw[0])
    return str(raw)


def run(args):
    # ── Load data ──────────────────────────────────────────────────────────
    tauber = load_tauber(force_refresh=args.refresh)
    print(f"[Tauber] {len(tauber):,} lemma entries loaded")

    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    by_lemma, by_strongs = load_our_lexemes(conn)
    print(f"[DB]     {len(by_lemma):,} lexeme rows loaded\n")

    # ── Analysis ───────────────────────────────────────────────────────────
    gap_lemmas        = []   # Tauber has no strongs for this lemma
    strongs_mismatch  = []   # Tauber strongs ≠ our strongs_id
    missing_from_db   = []   # Tauber lemma not found in our lexeme table
    gk_to_populate    = []   # (lexeme_id, gk_number) pairs ready to write

    for raw_lemma, entry in tauber.items():
        if not isinstance(entry, dict):
            continue

        lemma_nfc      = nfc(str(raw_lemma))
        tauber_strongs = strongs_fmt(entry.get("strongs"))
        tauber_gk      = gk_fmt(entry.get("gk"))

        our_entry = by_lemma.get(lemma_nfc)
        if our_entry is None:
            # also try by strongs as fallback
            if tauber_strongs:
                our_entry = by_strongs.get(tauber_strongs)

        if our_entry is None:
            missing_from_db.append({
                "lemma": raw_lemma,
                "tauber_strongs": tauber_strongs,
                "tauber_gk": tauber_gk,
            })
            continue

        # Track GK to populate
        if tauber_gk and not our_entry.get("gk_number"):
            gk_to_populate.append((our_entry["id"], tauber_gk))

        # Strong's gap lemmas
        if tauber_strongs is None:
            gap_lemmas.append({
                "lemma": raw_lemma,
                "our_strongs": our_entry["strongs_id"],
                "tauber_gk": tauber_gk,
            })
            continue

        # Strong's mismatch
        if our_entry["strongs_id"] and our_entry["strongs_id"] != tauber_strongs:
            strongs_mismatch.append({
                "lemma": raw_lemma,
                "our_strongs": our_entry["strongs_id"],
                "tauber_strongs": tauber_strongs,
                "tauber_gk": tauber_gk,
            })

    # ── Report ─────────────────────────────────────────────────────────────
    print("=" * 60)
    print("LEMMA COVERAGE VALIDATION REPORT")
    print("=" * 60)

    print(f"\n✓  Tauber total lemmas:          {len(tauber):>6,}")
    print(f"✓  Our lexeme rows:              {len(by_lemma):>6,}")
    print(f"✓  GK numbers to populate:       {len(gk_to_populate):>6,}")

    print(f"\n── Gap lemmas (no strongs in Tauber): {len(gap_lemmas)}")
    if gap_lemmas:
        for row in gap_lemmas[:20]:
            print(f"   {row['lemma']:25s} our_strongs={row['our_strongs']}  gk={row['tauber_gk']}")
        if len(gap_lemmas) > 20:
            print(f"   ... and {len(gap_lemmas) - 20} more")

    print(f"\n── Strong's mismatches: {len(strongs_mismatch)}")
    if strongs_mismatch:
        for row in strongs_mismatch[:20]:
            print(f"   {row['lemma']:25s}  ours={row['our_strongs']}  tauber={row['tauber_strongs']}  gk={row['tauber_gk']}")
        if len(strongs_mismatch) > 20:
            print(f"   ... and {len(strongs_mismatch) - 20} more")

    print(f"\n── Missing from our DB: {len(missing_from_db)}")
    if missing_from_db:
        for row in missing_from_db[:20]:
            print(f"   {row['lemma']:25s}  strongs={row['tauber_strongs']}  gk={row['tauber_gk']}")
        if len(missing_from_db) > 20:
            print(f"   ... and {len(missing_from_db) - 20} more")

    # ── Export ─────────────────────────────────────────────────────────────
    if args.export:
        export_data = {
            "gap_lemmas": gap_lemmas,
            "strongs_mismatches": strongs_mismatch,
            "missing_from_db": missing_from_db,
            "gk_mappings": [
                {"lexeme_id": lid, "gk_number": gk} for lid, gk in gk_to_populate
            ],
        }
        Path(args.export).write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[Export] Written to {args.export}")

    # ── Populate GK ────────────────────────────────────────────────────────
    if args.populate_gk:
        if not gk_to_populate:
            print("\n[GK] Nothing to populate — all gk_number fields already set.")
        else:
            print(f"\n[GK] Populating {len(gk_to_populate):,} gk_number values...")
            cur = conn.cursor()
            cur.executemany(
                "UPDATE lexeme SET gk_number = %s WHERE id = %s",
                [(gk, lid) for lid, gk in gk_to_populate],
            )
            conn.commit()
            print(f"[GK] Done — {cur.rowcount:,} rows updated.")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Validate lexeme coverage against Tauber's greek-lemma-mappings")
    parser.add_argument("--populate-gk", action="store_true",
                        help="Write GK numbers from Tauber into lexeme.gk_number")
    parser.add_argument("--export", metavar="FILE",
                        help="Export full report as JSON (e.g. data/tauber-report.json)")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-download Tauber's YAML even if cached")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
