"""Parse user-supplied per-hospital bed allotments (CSV or Excel).

Allotments are scenario assumptions entered by the user: beds set aside for
dengue, beds kept for non-dengue patients and temporary holding spaces. They
are never treated as verified capacity, vacancies or PhilHealth figures. Rows
are matched only to the approved QC hospital records; nothing is guessed.
"""
import csv
import io
import re
import zipfile

MAX_FILE_BYTES = 1_000_000
MAX_ROWS = 500
MAX_BEDS = 10000

HEADER_ALIASES = {
    "facilityId": {"facilityid", "hospitalid", "id"},
    "name": {"hospitalname", "hospital", "name", "facilityname"},
    "dengueBeds": {"denguebeds", "bedsfordengue", "dengue"},
    "nonDengueBeds": {"nondenguebeds", "bedsfornondengue", "nondengue", "otherbeds"},
    "holdingSpaces": {"holdingspaces", "holding", "temporaryholdingspaces", "holdingcapacity"},
    "extraDengueBeds": {"extradenguebeds", "extrabedsfordengue"},
    "extraNonDengueBeds": {"extranondenguebeds", "extrabedsfornondengue"},
    "dengueHoldingSpaces": {"dengueholdingspaces", "holdingfordengue", "holdingspacesfordengue"},
    "nonDengueHoldingSpaces": {"nondengueholdingspaces", "holdingfornondengue", "holdingspacesfornondengue"},
}
NUMBER_FIELDS = {"dengueBeds": "dengue beds", "nonDengueBeds": "non-dengue beds", "holdingSpaces": "holding spaces"}
# Optional columns: a blank cell keeps the scenario default.
OPTIONAL_FIELDS = {"extraDengueBeds": "extra dengue beds", "extraNonDengueBeds": "extra non-dengue beds",
                   "dengueHoldingSpaces": "dengue holding spaces", "nonDengueHoldingSpaces": "non-dengue holding spaces"}


class AllotmentFileError(ValueError):
    """The file as a whole cannot be read (format, size, missing columns)."""


def _key(text):
    return re.sub(r"[^a-z0-9]", "", str(text or "").casefold())


def _name_key(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").casefold()).split())


def read_table(content: bytes):
    """Return the first sheet / CSV as rows of cell strings."""
    if not content:
        raise AllotmentFileError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise AllotmentFileError("The file is larger than 1 MB.")
    if content[:4] == b"PK\x03\x04":
        return _read_xlsx(content)
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise AllotmentFileError("Old .xls files are not supported. Save the sheet as .xlsx or .csv.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AllotmentFileError("Save the CSV with UTF-8 encoding.") from None
    if "\x00" in text:
        raise AllotmentFileError("This does not look like a CSV or Excel (.xlsx) file.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx(content):
    from openpyxl import load_workbook
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            # Guard against decompression bombs before openpyxl inflates the sheet.
            if sum(info.file_size for info in archive.infolist()) > 20 * MAX_FILE_BYTES:
                raise AllotmentFileError("The Excel file expands to more than 20 MB.")
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except AllotmentFileError:
        raise
    except Exception:
        raise AllotmentFileError("The Excel file could not be read. Save it as .xlsx or .csv.") from None
    try:
        sheet = book.worksheets[0]
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(["" if cell is None else str(cell) for cell in row])
            if len(rows) > MAX_ROWS + 1:
                break
        return rows
    finally:
        book.close()


def _whole_number(text, label):
    value = str(text).strip().replace(",", "")
    if value == "":
        return None, f"{label} is missing."
    try:
        number = float(value)
    except ValueError:
        return None, f"{label} must be a number (got “{str(text).strip()[:20]}”)."
    if number != number or number in (float("inf"), float("-inf")) or number != int(number):
        return None, f"{label} must be a whole number."
    number = int(number)
    if not 0 <= number <= MAX_BEDS:
        return None, f"{label} must be between 0 and {MAX_BEDS:,}."
    return number, None


def parse_allotments(rows, hospitals):
    """Match rows to approved hospitals. Returns allotments, row errors and hospitals not in the file."""
    rows = [row for row in rows if any(str(cell).strip() for cell in row)]
    if not rows:
        raise AllotmentFileError("The file has no rows.")
    if len(rows) > MAX_ROWS + 1:
        raise AllotmentFileError(f"The file has more than {MAX_ROWS} rows.")
    columns = {}
    for index, header in enumerate(rows[0]):
        for field, aliases in HEADER_ALIASES.items():
            if _key(header) in aliases and field not in columns:
                columns[field] = index
    missing = [label for field, label in NUMBER_FIELDS.items() if field not in columns]
    if "facilityId" not in columns and "name" not in columns:
        missing.insert(0, "facility_id or hospital_name")
    if missing:
        raise AllotmentFileError("Missing column(s): " + ", ".join(missing) + ". Use the template's header row.")
    by_id = {h["id"]: h for h in hospitals}
    by_name = {}
    for h in hospitals:
        by_name.setdefault(_name_key(h["name"]), []).append(h)

    def cell(row, field):
        index = columns.get(field)
        return row[index].strip() if index is not None and index < len(row) else ""

    allotments, errors, seen = [], [], {}
    for line, row in enumerate(rows[1:], start=2):
        ident, name = cell(row, "facilityId").upper(), cell(row, "name")
        if ident:
            hospital = by_id.get(ident)
            if not hospital:
                errors.append({"row": line, "message": f"Unknown facility ID “{ident[:20]}”. Use an ID from the template."})
                continue
        else:
            matches = by_name.get(_name_key(name), [])
            if len(matches) != 1:
                errors.append({"row": line, "message": "Hospital name not found exactly; add its facility ID." if not matches else "Hospital name matches more than one site; add its facility ID."})
                continue
            hospital = matches[0]
        if hospital["id"] in seen:
            errors.append({"row": line, "message": f"{hospital['id']} already appears on row {seen[hospital['id']]}."})
            continue
        values, problems = {}, []
        for field, label in NUMBER_FIELDS.items():
            values[field], problem = _whole_number(cell(row, field), label.capitalize())
            if problem:
                problems.append(problem)
        for field, label in OPTIONAL_FIELDS.items():
            if field in columns and cell(row, field) != "":
                values[field], problem = _whole_number(cell(row, field), label.capitalize())
                if problem:
                    problems.append(problem)
        if not problems:
            # Holding split: a dengue or non-dengue part (or both, summing to the total) of holding_spaces.
            dengue_hold, other_hold = values.pop("dengueHoldingSpaces", None), values.pop("nonDengueHoldingSpaces", None)
            if dengue_hold is not None and other_hold is None:
                other_hold = values["holdingSpaces"] - dengue_hold
            if other_hold is not None and (other_hold < 0 or other_hold > values["holdingSpaces"]
                                           or (dengue_hold is not None and dengue_hold + other_hold != values["holdingSpaces"])):
                problems.append("Dengue plus non-dengue holding spaces must equal holding spaces.")
            elif other_hold is not None:
                values["nonDengueHoldingSpaces"] = other_hold
        if not problems and values["dengueBeds"] + values["nonDengueBeds"] < 1:
            problems.append("Dengue plus non-dengue beds must be at least 1.")
        if not problems and values["dengueBeds"] + values["nonDengueBeds"] > MAX_BEDS:
            problems.append(f"Total beds must be at most {MAX_BEDS:,}.")
        if problems:
            errors.append({"row": line, "message": " ".join(problems)})
            continue
        seen[hospital["id"]] = line
        allotments.append({"facilityId": hospital["id"], "name": hospital["name"], **values})
    allotments.sort(key=lambda a: a["facilityId"])
    not_in_file = sorted(set(by_id) - set(seen))
    return {"allotments": allotments, "errors": errors, "hospitalsNotInFile": not_in_file}
