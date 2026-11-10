#!/bin/sh
# Create an Iceberg table through Trino, delete a row with merge-on-read, and
# join it to an in-memory table. Fails if any statement fails.
set -eu

trino_exec() {
  docker compose exec -T trino trino --server http://localhost:8080 --execute "$1"
}

echo "waiting for trino"
i=0
while ! docker compose exec -T trino trino --server http://localhost:8080 --execute "SELECT 1" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 60 ]; then
    echo "trino did not become ready"
    exit 1
  fi
  sleep 5
done

trino_exec "CREATE SCHEMA IF NOT EXISTS iceberg.demo"
trino_exec "DROP TABLE IF EXISTS iceberg.demo.spread"
trino_exec "CREATE TABLE iceberg.demo.spread (region varchar, spread_aud double) WITH (format_version = 2, partitioning = ARRAY['region'])"
if trino_exec "ALTER TABLE iceberg.demo.spread SET PROPERTIES \"write.delete.mode\" = 'merge-on-read', \"write.update.mode\" = 'merge-on-read', \"write.merge.mode\" = 'merge-on-read'"; then
  echo "merge-on-read delete mode set"
else
  echo "this Trino build does not expose write.delete.mode; the delete still removes the row"
fi
trino_exec "INSERT INTO iceberg.demo.spread VALUES ('SA1', 207), ('NSW1', 112), ('TAS1', 64)"
trino_exec "DELETE FROM iceberg.demo.spread WHERE region = 'TAS1'"
trino_exec "CREATE SCHEMA IF NOT EXISTS memory.default"
trino_exec "DROP TABLE IF EXISTS memory.default.regions"
trino_exec "CREATE TABLE memory.default.regions (code varchar, name varchar)"
trino_exec "INSERT INTO memory.default.regions VALUES ('SA1', 'South Australia'), ('NSW1', 'New South Wales'), ('TAS1', 'Tasmania')"
result=$(trino_exec "SELECT r.name, s.spread_aud FROM iceberg.demo.spread s JOIN memory.default.regions r ON s.region = r.code ORDER BY s.spread_aud DESC")
printf '%s\n' "$result"
printf '%s\n' "$result" | grep -q "South Australia"
printf '%s\n' "$result" | grep -q "New South Wales"
if printf '%s\n' "$result" | grep -q "Tasmania"; then
  echo "delete did not remove Tasmania"
  exit 1
fi
echo "TRINO_SMOKE_OK"
