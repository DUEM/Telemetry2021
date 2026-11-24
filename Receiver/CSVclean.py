"""Filter telemetry CSV logs down to a single message ID.

TEMPORARY SOLUTION: a quick analysis tool for looking at logged data until
a proper one is built. It assumes the current hex2csv.py layout (no header,
ID in column 2, key/value pairs from column 4) and may need changing if the
.BIN format changes.

Reads every .csv file in a folder, lists the message IDs found in the
second column, asks the user to pick one, and writes a new CSV that
contains only the rows with that ID (in the same format as the input).
It then asks which field of that message to plot, and plots it against
time with matplotlib. The line is broken wherever readings are more than
GAP_SECONDS apart, so missing data is not drawn as a straight line.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl

DEFAULT_ID_COLUMN = 2  # 2nd column: message name, e.g. PackParameters
PREVIEW_ROWS = 3
GAP_SECONDS = 2  # break the plotted line where readings are further apart


def read_csvs(folder):
    """Read all CSV files in a folder into one DataFrame."""
    files = sorted(Path(folder).glob("*.csv"))
    if not files:
        raise SystemExit(f"No CSV files found in {folder}")

    frames = []
    for file in files:
        print(f"Reading {file}")
        # No header row; read everything as text so nothing gets altered
        frames.append(pl.read_csv(file, has_header=False, infer_schema=False))
    return pl.concat(frames, how="diagonal")


def preview(df):
    """Print the first few rows, one line per column, with column numbers.

    The CSVs are too wide to show as normal rows in a terminal, so the
    table is turned on its side: each line is a column, each cell a row.
    """
    head = df.head(PREVIEW_ROWS)
    print(f"\nFirst {head.height} rows (one line per column):")
    print("  Col  " + "".join(f"Row {r + 1:<24}" for r in range(head.height)))
    for number, name in enumerate(head.columns, start=1):
        cells = ["" if v is None else v[:26] for v in head[name].to_list()]
        print(f"  {number:>3}  " + "".join(f"{c:<28}" for c in cells))


def choose_column(df):
    """Ask which column holds the IDs to filter on."""
    while True:
        choice = input(
            f"\nWhich column holds the IDs? [{DEFAULT_ID_COLUMN}]: "
        ).strip() or str(DEFAULT_ID_COLUMN)
        if choice.isdigit() and 1 <= int(choice) <= df.width:
            return f"column_{choice}"
        print(f"Enter a column number from 1 to {df.width}.")


def choose_id(df, id_column):
    """Show every ID with its row count and ask the user to pick one."""
    counts = (
        df.drop_nulls(id_column).group_by(id_column).len().sort(id_column)
    )
    ids = counts[id_column].to_list()

    print("\nIDs found:")
    for number, (name, count) in enumerate(counts.iter_rows(), start=1):
        print(f"  {number:>3}. {name} ({count} rows)")

    while True:
        choice = input("\nEnter the number or name of the ID to keep: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(ids):
            return ids[int(choice) - 1]
        if choice in ids:
            return choice
        print("Not a valid choice, try again.")


def to_long(df):
    """Turn the key/value pair columns into rows of (time, key, value).

    Columns 4 onwards hold pairs like VoltageIn,88.1,CurrentIn,0.0 and the
    last two columns are a status flag and a counter, so they are skipped.
    """
    last_pair_col = df.width - 2
    pairs = [
        (f"column_{i}", f"column_{i + 1}")
        for i in range(4, last_pair_col, 2)
    ]
    long = pl.concat([
        df.select(
            pl.col("column_1").alias("time"),
            pl.col(key).alias("key"),
            pl.col(value).alias("value"),
        )
        for key, value in pairs
    ])
    return long.drop_nulls("key").with_columns(
        pl.col("time").str.strptime(pl.Datetime, "%d/%m/%Y %H:%M:%S%.f"),
        pl.col("value").cast(pl.Float64, strict=False),
    )


def choose_field(long):
    """List the fields in the chosen message and ask which one to plot."""
    fields = long["key"].unique(maintain_order=True).to_list()

    print("\nFields available to plot:")
    for number, name in enumerate(fields, start=1):
        print(f"  {number:>3}. {name}")

    while True:
        choice = input("\nEnter the number or name of the field to plot: ")
        choice = choice.strip()
        if choice.isdigit() and 1 <= int(choice) <= len(fields):
            return fields[int(choice) - 1]
        if choice in fields:
            return choice
        print("Not a valid choice, try again.")


def plot_field(long, message_id, field):
    """Plot one field against time with matplotlib."""
    data = long.filter(pl.col("key") == field).drop_nulls("value")
    data = data.sort("time")
    if data.is_empty():
        print(f"{field} has no numeric values to plot.")
        return

    # Start a new segment wherever readings are more than GAP_SECONDS apart,
    # so missing data shows as a gap rather than a straight line across it
    gap_ms = pl.col("time").diff().dt.total_milliseconds()
    data = data.with_columns(
        segment=(gap_ms > GAP_SECONDS * 1000).fill_null(False).cum_sum()
    )

    plt.figure(figsize=(10, 5))
    for segment in data.partition_by("segment", maintain_order=True):
        plt.plot(
            segment["time"].to_list(),
            segment["value"].to_list(),
            color="tab:blue",
            marker=".",
        )
    plt.title(f"{message_id}: {field} (line broken at gaps > {GAP_SECONDS}s)")
    plt.xlabel("Time")
    plt.ylabel(field)
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def main():
    folder = input("Folder containing the CSV files [Tests/data]: ").strip()
    df = read_csvs(folder or "Tests/data")

    preview(df)
    id_column = choose_column(df)
    chosen = choose_id(df, id_column)
    filtered = df.filter(pl.col(id_column) == chosen)

    safe_name = "".join(c if c.isalnum() else "_" for c in chosen)
    default_out = f"{safe_name}.csv"
    out = input(f"Output file name [{default_out}]: ").strip() or default_out
    filtered.write_csv(out, include_header=False)
    print(f"Wrote {filtered.height} rows to {out}")

    long = to_long(filtered)
    field = choose_field(long)
    plot_field(long, chosen, field)


if __name__ == "__main__":
    main()
