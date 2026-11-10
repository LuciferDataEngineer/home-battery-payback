"""Event-time windows over NEM prices.

The SQL job uses TUMBLE and HOP with a source watermark. Allowed lateness is the
lag on the punctuated watermark: a row inside the lag is counted, a row outside
it is dropped once the watermark has passed the window. That behaviour is asserted
in tests/test_flink.py.

PyFlink's Python window operator does not observe watermarks in embedded or
process mode (the operator's current watermark stays at Long.MIN_VALUE), so the
window itself runs in the Java SQL engine, which does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from hbp.config import ROOT

JAVA_SRC = ROOT / "src" / "hbp" / "java" / "PunctuatedWatermarks.java"
_READY = False


def _pyflink_lib() -> Path:
    for entry in sys.path:
        lib = Path(entry) / "pyflink" / "lib"
        if lib.is_dir():
            return lib
    raise RuntimeError("apache-flink is not installed. Use Python 3.11 and pip install apache-flink==2.1.1")


def prepare_runtime() -> None:
    """Compile the watermark helper onto the PyFlink classpath before the JVM starts."""
    global _READY
    if _READY:
        return
    lib = _pyflink_lib()
    jar_path = lib / "hbp-watermarks.jar"
    build = ROOT / "data" / "output" / "flink-classes"
    if build.exists():
        import shutil

        shutil.rmtree(build)
    build.mkdir(parents=True)
    java_home = os.environ.get("JAVA_HOME", "")
    javac = str(Path(java_home) / "bin" / "javac") if java_home else "javac"
    jar_bin = str(Path(java_home) / "bin" / "jar") if java_home else "jar"
    if not Path(javac).exists():
        javac, jar_bin = "javac", "jar"
    jars = [str(path) for path in sorted(lib.glob("*.jar")) if path.name != jar_path.name]
    subprocess.check_call(
        [javac, "--release", "17", "-proc:none", "-cp", os.pathsep.join(jars), "-d", str(build), str(JAVA_SRC)],
    )
    subprocess.check_call([jar_bin, "cf", str(jar_path), "-C", str(build), "hbp"])
    # Importing pyflink starts the gateway JVM, which globs pyflink/lib/*.jar.
    import pyflink  # noqa: F401

    _READY = True


def _view_from_rows(t_env, rows: list[tuple[int, int, str]], lag_ms: int) -> None:
    from pyflink.common import Types, WatermarkStrategy
    from pyflink.common.watermark_strategy import TimestampAssigner
    from pyflink.java_gateway import get_gateway
    from pyflink.table import Schema

    class Assigner(TimestampAssigner):
        def extract_timestamp(self, value, record_timestamp: int) -> int:
            return int(value[0])

    stream_env = _STASH["env"]
    source = stream_env.from_collection(
        rows,
        type_info=Types.ROW_NAMED(
            ["event_ms", "rrp", "region"],
            [Types.LONG(), Types.INT(), Types.STRING()],
        ),
    )
    strategy = WatermarkStrategy(
        get_gateway().jvm.hbp.PunctuatedWatermarks(int(lag_ms))
    ).with_timestamp_assigner(Assigner())
    watermarked = source.assign_timestamps_and_watermarks(strategy)
    schema = (
        Schema.new_builder()
        .column("region", "STRING")
        .column("rrp", "INT")
        .column_by_expression("event_time", "TO_TIMESTAMP_LTZ(event_ms, 3)")
        .watermark("event_time", "SOURCE_WATERMARK()")
        .build()
    )
    t_env.create_temporary_view("prices", t_env.from_data_stream(watermarked, schema))


_STASH: dict = {}


def _open(rows: list[tuple[int, int, str]], lag_ms: int):
    from pyflink.datastream import StreamExecutionEnvironment
    from pyflink.table import StreamTableEnvironment

    prepare_runtime()
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    t_env = StreamTableEnvironment.create(env)
    _STASH["env"] = env
    _view_from_rows(t_env, rows, lag_ms)
    return t_env


def tumble_sums(rows: list[tuple[int, int, str]], lag_ms: int, window_minutes: int = 10) -> list[tuple]:
    t_env = _open(rows, lag_ms)
    query = f"""
        SELECT CAST(window_start AS STRING) AS window_start,
               SUM(rrp) AS sum_rrp,
               COUNT(*) AS n
        FROM TABLE(
          TUMBLE(TABLE prices, DESCRIPTOR(event_time), INTERVAL '{int(window_minutes)}' MINUTES)
        )
        GROUP BY window_start, window_end
    """
    collected = []
    for row in t_env.sql_query(query).execute().collect():
        collected.append((str(row[0]), int(row[1]), int(row[2])))
    return collected


def hop_averages(rows: list[tuple[int, int, str]], lag_ms: int = 1) -> list[tuple]:
    t_env = _open(rows, lag_ms)
    query = """
        SELECT CAST(window_start AS STRING) AS window_start,
               CAST(window_end AS STRING) AS window_end,
               AVG(rrp) AS avg_rrp,
               COUNT(*) AS n
        FROM TABLE(
          HOP(
            DATA => TABLE prices,
            TIMECOL => DESCRIPTOR(event_time),
            SLIDE => INTERVAL '30' MINUTES,
            SIZE => INTERVAL '2' HOURS
          )
        )
        GROUP BY window_start, window_end
    """
    collected = []
    for row in t_env.sql_query(query).execute().collect():
        collected.append((str(row[0]), str(row[1]), float(row[2]), int(row[3])))
    return collected


def daily_extrema(rows: list[tuple[int, float, str]]) -> list[tuple]:
    """TUMBLE of one day. rows are (epoch_ms, rrp, region). rrp may be fractional.

    The SQL sum/avg path above uses INT rrp for the lateness fixture. This path
    casts rrp to DOUBLE so real AEMO prices keep their cents.
    """
    prepare_runtime()
    from pyflink.common import Types, WatermarkStrategy
    from pyflink.common.watermark_strategy import TimestampAssigner
    from pyflink.datastream import StreamExecutionEnvironment
    from pyflink.java_gateway import get_gateway
    from pyflink.table import Schema, StreamTableEnvironment

    class Assigner(TimestampAssigner):
        def extract_timestamp(self, value, record_timestamp: int) -> int:
            return int(value[0])

    # Reuse an int-cent representation to stay on the same SQL types as the fixture,
    # then scale back. Cents are exact for two-decimal RRP.
    cents = [(int(ts), int(round(rrp * 100)), region) for ts, rrp, region in rows]
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    _STASH["env"] = env
    t_env = StreamTableEnvironment.create(env)
    source = env.from_collection(
        cents,
        type_info=Types.ROW_NAMED(
            ["event_ms", "rrp_cents", "region"],
            [Types.LONG(), Types.INT(), Types.STRING()],
        ),
    )
    strategy = WatermarkStrategy(get_gateway().jvm.hbp.PunctuatedWatermarks(1)).with_timestamp_assigner(
        Assigner()
    )
    watermarked = source.assign_timestamps_and_watermarks(strategy)
    schema = (
        Schema.new_builder()
        .column("region", "STRING")
        .column("rrp_cents", "INT")
        .column_by_expression("event_time", "TO_TIMESTAMP_LTZ(event_ms, 3)")
        .watermark("event_time", "SOURCE_WATERMARK()")
        .build()
    )
    t_env.create_temporary_view("prices_cents", t_env.from_data_stream(watermarked, schema))
    query = """
        SELECT region,
               CAST(window_start AS STRING) AS window_start,
               MIN(rrp_cents) AS trough_cents,
               MAX(rrp_cents) AS peak_cents,
               COUNT(*) AS n,
               SUM(CASE WHEN rrp_cents < 0 THEN 1 ELSE 0 END) AS negative_intervals
        FROM TABLE(
          TUMBLE(TABLE prices_cents, DESCRIPTOR(event_time), INTERVAL '1' DAY)
        )
        GROUP BY region, window_start, window_end
    """
    collected = []
    for row in t_env.sql_query(query).execute().collect():
        collected.append(
            (str(row[0]), str(row[1]), int(row[2]) / 100.0, int(row[3]) / 100.0, int(row[4]), int(row[5]))
        )
    return collected
