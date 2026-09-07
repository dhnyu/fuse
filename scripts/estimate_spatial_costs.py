#!/usr/bin/env python3
import argparse
import csv
import sqlite3


def counts(path, table, rows):
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    query = (
        f'SELECT count(*) FROM "rtree_{table}_geom" '
        'WHERE maxx >= ? AND minx <= ? AND maxy >= ? AND miny <= ?'
    )
    values = [connection.execute(query, (r[1], r[3], r[2], r[4])).fetchone()[0] for r in rows]
    connection.close()
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", required=True)
    parser.add_argument("--building", required=True)
    parser.add_argument("--road", required=True)
    parser.add_argument("--poi", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.scenes, newline="", encoding="utf-8") as stream:
        rows = [(r[0], *map(float, r[1:])) for r in csv.reader(stream, delimiter="\t")]
    building = counts(args.building, "buildings", rows)
    road = counts(args.road, "links", rows)
    poi = counts(args.poi, "points", rows)
    with open(args.output, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("scene_id", "building", "road", "poi"))
        writer.writerows((r[0], b, d, p) for r, b, d, p in zip(rows, building, road, poi))


if __name__ == "__main__":
    main()
