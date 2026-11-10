"""Refresh data/snapshot from the public sources, or from a local cache of those files.

`make ingest` downloads. CI never calls this: it reads the committed snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from urllib.request import urlopen

import duckdb

from hbp.config import ACCESS_DATE, SNAPSHOT

CER_BATTERY_INSTALLS = (
    "https://cer.gov.au/document/sgu-battery-installations-2011-to-present-and-totals"
)
CER_BATTERY_CAPACITY = (
    "https://cer.gov.au/document/sgu-battery-capacity-2011-to-present-and-totals"
)
CER_SOLAR_INSTALLS = (
    "https://cer.gov.au/document/sgu-solar-installations-2011-to-present-and-totals"
)
ABS_GCP_POA = (
    "https://www.abs.gov.au/census/find-census-data/datapacks/download/"
    "2021_GCP_POA_for_AUS_short-header.zip"
)
AEMO_TEMPLATE = (
    "https://aemo.com.au/aemo/data/nem/priceanddemand/PRICE_AND_DEMAND_{yyyymm}_{region}.csv"
)
REGIONS = ("NSW1", "QLD1", "VIC1", "SA1", "TAS1")
# Twelve complete months ending October 2026. November 2026 was not a full month
# on the access date.
MONTHS = (
    "202511",
    "202512",
    "202601",
    "202602",
    "202603",
    "202604",
    "202605",
    "202606",
    "202607",
    "202608",
    "202609",
    "202610",
)

SOURCES = {
    "cer_battery_installations.csv": {
        "publisher": "Clean Energy Regulator",
        "url": CER_BATTERY_INSTALLS,
        "licence": "CC BY 4.0",
        "licence_note": (
            "Based on Clean Energy Regulator material licensed under a "
            "Creative Commons Attribution 4.0 licence. "
            "https://cer.gov.au/about-us/our-policies/copyright"
        ),
        "coverage": "Battery installations by postcode, July 2025 to September 2026",
    },
    "cer_battery_capacity.csv": {
        "publisher": "Clean Energy Regulator",
        "url": CER_BATTERY_CAPACITY,
        "licence": "CC BY 4.0",
        "licence_note": (
            "Based on Clean Energy Regulator material licensed under a "
            "Creative Commons Attribution 4.0 licence."
        ),
        "coverage": "Usable battery kWh by postcode, July 2025 to September 2026",
    },
    "cer_solar_installations.csv": {
        "publisher": "Clean Energy Regulator",
        "url": CER_SOLAR_INSTALLS,
        "licence": "CC BY 4.0",
        "licence_note": (
            "Based on Clean Energy Regulator material licensed under a "
            "Creative Commons Attribution 4.0 licence."
        ),
        "coverage": "Small-scale solar PV installations by postcode, 2001 to September 2026",
    },
    "abs_poa_occupied_dwellings_2021.csv": {
        "publisher": "Australian Bureau of Statistics",
        "url": ABS_GCP_POA,
        "licence": "CC BY 4.0",
        "licence_note": (
            "Extract of column Total_dwelings from 2021 Census General Community Profile "
            "table G34 (2021Census_G34_AUST_POA.csv) for Postal Areas. "
            "Based on Australian Bureau of Statistics data, CC BY 4.0."
        ),
        "coverage": "Occupied private dwellings by 2021 postal area, Census night 10 August 2021",
    },
    "aemo_price_demand_202511_202610.parquet": {
        "publisher": "Australian Energy Market Operator",
        "url": "https://aemo.com.au/aemo/data/nem/priceanddemand/",
        "licence": "AEMO copyright permission with attribution",
        "licence_note": (
            "AEMO confirms its general permission for anyone to use AEMO Material for any "
            "purpose, but only with accurate and appropriate attribution of the relevant "
            "AEMO Material and AEMO as its author. "
            "https://www.aemo.com.au/privacy-and-legal-notices/copyright-permissions. "
            "This file is a columnar copy of the monthly PRICE_AND_DEMAND CSVs for "
            "NSW1, QLD1, VIC1, SA1 and TAS1 from November 2025 to October 2026."
        ),
        "coverage": "5-minute regional reference price and demand, 1 Nov 2025 to 31 Oct 2026",
    },
}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=120) as response:  # noqa: S310 - public data files
        dest.write_bytes(response.read())


def _dwellings_from_zip(zip_path: Path, dest: Path) -> int:
    member = "2021 Census GCP Postal Areas for AUS/2021Census_G34_AUST_POA.csv"
    with zipfile.ZipFile(zip_path) as archive, archive.open(member) as handle:
        import csv

        reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))
        rows = []
        for record in reader:
            code = record["POA_CODE_2021"].strip()
            if code.upper().startswith("POA"):
                code = code[3:]
            rows.append((code.zfill(4), int(record["Total_dwelings"] or 0)))
    dest.write_text(
        "postcode,occupied_private_dwellings\n"
        + "\n".join(f"{code},{count}" for code, count in rows)
        + "\n"
    )
    return len(rows)


def _prices_from_dir(price_dir: Path, dest: Path) -> int:
    files = sorted(price_dir.glob("PRICE_AND_DEMAND_*.csv"))
    if len(files) != 60:
        raise FileNotFoundError(f"Expected 60 price files in {price_dir}, found {len(files)}")
    con = duckdb.connect()
    con.execute(
        """
        COPY (
          SELECT REGION AS region,
                 strptime(SETTLEMENTDATE, '%Y/%m/%d %H:%M:%S') AS ts,
                 RRP::DOUBLE AS rrp,
                 TOTALDEMAND::DOUBLE AS demand
          FROM read_csv(
            ?,
            header = true,
            union_by_name = true,
            filename = true,
            types = {
              'REGION': 'VARCHAR',
              'SETTLEMENTDATE': 'VARCHAR',
              'TOTALDEMAND': 'DOUBLE',
              'RRP': 'DOUBLE',
              'PERIODTYPE': 'VARCHAR'
            }
          )
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(price_dir / "PRICE_AND_DEMAND_*.csv"), str(dest)],
    )
    count = con.execute("SELECT count(*) FROM read_parquet(?)", [str(dest)]).fetchone()[0]
    con.close()
    return int(count)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> int:
    if path.suffix == ".parquet":
        con = duckdb.connect()
        count = con.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
        con.close()
        return int(count)
    # header excluded
    with path.open() as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def write_manifest() -> None:
    files = []
    for name, meta in SOURCES.items():
        path = SNAPSHOT / name
        files.append(
            {
                "file": name,
                "publisher": meta["publisher"],
                "url": meta["url"],
                "licence": meta["licence"],
                "licence_note": meta["licence_note"],
                "coverage": meta["coverage"],
                "access_date": ACCESS_DATE,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "rows": _rows(path),
            }
        )
    document = {
        "built": ACCESS_DATE,
        "note": (
            "Offline pipeline input. Regenerated by `make ingest`. "
            "Do not edit the data files by hand; the sha256 checks will fail."
        ),
        "files": files,
    }
    (SNAPSHOT / "MANIFEST.json").write_text(json.dumps(document, indent=2) + "\n")


def build_from_cache(cache: Path) -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    copies = {
        "cer_battery_installations.csv": cache / "battery_installs.csv",
        "cer_battery_capacity.csv": cache / "battery_capacity.csv",
        "cer_solar_installations.csv": cache / "solar_installs.csv",
    }
    for name, source in copies.items():
        if not source.exists():
            raise FileNotFoundError(source)
        (SNAPSHOT / name).write_bytes(source.read_bytes())
    _dwellings_from_zip(cache / "gcp_poa.zip", SNAPSHOT / "abs_poa_occupied_dwellings_2021.csv")
    _prices_from_dir(cache / "prices", SNAPSHOT / "aemo_price_demand_202511_202610.parquet")
    write_manifest()


def download_live(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "prices").mkdir(exist_ok=True)
    _download(CER_BATTERY_INSTALLS, cache / "battery_installs.csv")
    _download(CER_BATTERY_CAPACITY, cache / "battery_capacity.csv")
    _download(CER_SOLAR_INSTALLS, cache / "solar_installs.csv")
    _download(ABS_GCP_POA, cache / "gcp_poa.zip")
    for yyyymm in MONTHS:
        for region in REGIONS:
            url = AEMO_TEMPLATE.format(yyyymm=yyyymm, region=region)
            dest = cache / "prices" / f"PRICE_AND_DEMAND_{yyyymm}_{region}.csv"
            if not dest.exists():
                _download(url, dest)
    build_from_cache(cache)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the committed data snapshot")
    parser.add_argument("--cache", type=Path, default=Path("/tmp/hbp-raw"))
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Build the snapshot from files already in --cache instead of downloading",
    )
    args = parser.parse_args()
    if args.from_cache:
        build_from_cache(args.cache)
    else:
        download_live(args.cache)
    print(f"snapshot written {date.today().isoformat()} -> {SNAPSHOT}")


if __name__ == "__main__":
    main()
