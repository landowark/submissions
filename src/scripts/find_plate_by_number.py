import csv
import sys


def find_plate(csv_path: str, plate_number: int) -> str | None:
    with open(csv_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row.get("plate_number") is not None and int(row["plate_number"]) == plate_number:
                return row.get("plate")
    return None


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python find_plate_by_number.py <csv_file_path> <plate_number>")
        raise SystemExit(1)

    csv_path = sys.argv[1]
    try:
        plate_number = int(sys.argv[2])
    except ValueError:
        print("plate_number must be an integer.")
        raise SystemExit(1)

    plate = find_plate(csv_path, plate_number)
    if plate is None:
        print(f"NA{plate_number}")
    else:
        print(plate)


if __name__ == "__main__":
    main()
