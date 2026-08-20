#!/usr/bin/env python3
"""Copy filtered canonical attribute tables into a spatial subset GeoPackage."""

import argparse
import sqlite3
import sys


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def clone_table(connection, table, select_sql):
    create_sql = connection.execute(
        "SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if create_sql is None:
        raise RuntimeError(f"source table missing: {table}")
    connection.execute(create_sql[0])
    columns = [row[1] for row in connection.execute(f"PRAGMA src.table_info({quote(table)})")]
    column_sql = ",".join(quote(column) for column in columns)
    source_columns = ",".join(f"a.{quote(column)}" for column in columns)
    connection.execute(
        f"INSERT INTO {quote(table)} ({column_sql}) "
        f"{select_sql.format(source_columns=source_columns)}"
    )
    content = connection.execute(
        "SELECT table_name,data_type,identifier,description,last_change,min_x,min_y,max_x,max_y,srs_id "
        "FROM src.gpkg_contents WHERE table_name=?", (table,)
    ).fetchone()
    if content is None:
        raise RuntimeError(f"gpkg_contents entry missing: {table}")
    connection.execute(
        "INSERT INTO gpkg_contents "
        "(table_name,data_type,identifier,description,last_change,min_x,min_y,max_x,max_y,srs_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", content
    )


def copy_poi(connection):
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_points_nf_id ON points(NF_ID)")
    clone_table(
        connection,
        "addresses",
        "SELECT {source_columns} FROM src.addresses a JOIN points p ON p.NF_ID=a.NF_ID",
    )
    clone_table(
        connection,
        "foreign_names",
        "SELECT {source_columns} FROM src.foreign_names a JOIN points p ON p.NF_ID=a.NF_ID",
    )
    clone_table(
        connection,
        "aliases",
        "SELECT {source_columns} FROM src.aliases a JOIN points p ON p.NF_ID=a.POIID",
    )
    clone_table(connection, "category_lookup", "SELECT {source_columns} FROM src.category_lookup a")
    connection.execute("CREATE INDEX idx_addresses_nf_id ON addresses(NF_ID)")
    connection.execute("CREATE INDEX idx_foreign_names_nf_id ON foreign_names(NF_ID)")
    connection.execute("CREATE INDEX idx_aliases_poiid ON aliases(POIID)")


def copy_road(connection):
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_links_link_id ON links(LINK_ID)")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_node_id ON nodes(NODE_ID)")
    clone_table(
        connection,
        "multilink",
        "SELECT {source_columns} FROM src.multilink a JOIN links l ON l.LINK_ID=a.LINK_ID",
    )
    clone_table(
        connection,
        "turninfo",
        "SELECT {source_columns} FROM src.turninfo a "
        "JOIN nodes n ON n.NODE_ID=a.NODE_ID "
        "JOIN links s ON s.LINK_ID=a.ST_LINK "
        "JOIN links e ON e.LINK_ID=a.ED_LINK",
    )
    connection.execute("CREATE INDEX idx_multilink_link_id ON multilink(LINK_ID)")
    connection.execute("CREATE INDEX idx_turninfo_node_id ON turninfo(NODE_ID)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("poi", "road"))
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    connection = sqlite3.connect(args.destination)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("ATTACH DATABASE ? AS src", (args.source,))
        connection.execute("BEGIN IMMEDIATE")
        if args.mode == "poi":
            copy_poi(connection)
        else:
            copy_road(connection)
        connection.commit()
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {result}")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise
