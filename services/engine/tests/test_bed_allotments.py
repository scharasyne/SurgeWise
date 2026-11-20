"""Imported per-hospital bed allotments: parsing, validation and engine use.

Fixtures are constructed planning assumptions, not source observations.
"""
import io

from fastapi.testclient import TestClient
import pytest

from services.engine.main import app
from services.engine.api.qc_simulation import default_workspace
from services.engine.domain.bed_allotments import AllotmentFileError, parse_allotments, read_table
from services.engine.domain.patient_flow import simulate_flow

HOSPITALS = [{"id": "HOSP-614", "name": "Alpha General Hospital"}, {"id": "HOSP-615", "name": "Beta Medical Center, Inc."},
             {"id": "HOSP-616", "name": "Gamma Hospital"}]


def parse(text):
    return parse_allotments(read_table(text.encode()), HOSPITALS)


def test_csv_rows_match_by_id_or_exact_name_and_report_missing_hospitals():
    result = parse("facility_id,hospital_name,dengue_beds,non_dengue_beds,holding_spaces\n"
                   "hosp-614,anything,5,15,3\n,beta medical center inc,\"1,200\",800,0\n")
    assert result["allotments"] == [
        {"facilityId": "HOSP-614", "name": "Alpha General Hospital", "dengueBeds": 5, "nonDengueBeds": 15, "holdingSpaces": 3},
        {"facilityId": "HOSP-615", "name": "Beta Medical Center, Inc.", "dengueBeds": 1200, "nonDengueBeds": 800, "holdingSpaces": 0}]
    assert result["errors"] == [] and result["hospitalsNotInFile"] == ["HOSP-616"]


def test_header_aliases_semicolons_and_blank_rows_are_accepted():
    result = parse("Hospital ID;Beds for dengue;Beds for non-dengue;Temporary holding spaces\n\nHOSP-616;2;8;1\n")
    assert [a["facilityId"] for a in result["allotments"]] == ["HOSP-616"]


@pytest.mark.parametrize("row, message", [
    ("HOSP-999,1,1,1", "Unknown facility ID"), ("HOSP-614,-1,5,0", "between 0"), ("HOSP-614,2.5,5,0", "whole number"),
    ("HOSP-614,abc,5,0", "must be a number"), ("HOSP-614,,5,0", "missing"), ("HOSP-614,0,0,0", "at least 1"),
    ("HOSP-614,6000,6000,0", "at most"),
])
def test_invalid_rows_are_reported_with_row_numbers_and_never_zero_filled(row, message):
    result = parse("facility_id,dengue_beds,non_dengue_beds,holding_spaces\n" + row + "\n")
    assert result["allotments"] == []
    assert result["errors"][0]["row"] == 2 and message in result["errors"][0]["message"]


def test_duplicates_and_unknown_names_are_rejected():
    result = parse("facility_id,hospital_name,dengue_beds,non_dengue_beds,holding_spaces\n"
                   "HOSP-614,,1,1,0\n,Alpha General Hospital,2,2,0\n,Nowhere Clinic,1,1,0\n")
    assert len(result["allotments"]) == 1
    assert [e["row"] for e in result["errors"]] == [3, 4]


@pytest.mark.parametrize("content, message", [
    (b"", "empty"), (b"facility_id,dengue_beds\nHOSP-614,1\n", "Missing column"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", ".xls"), (b"x" * 1_000_001, "1 MB"), (b"PK\x03\x04broken", "could not be read"),
], ids=["empty", "missing-columns", "legacy-xls", "too-large", "corrupt-xlsx"])
def test_unreadable_files_raise_a_clear_message(content, message):
    with pytest.raises(AllotmentFileError, match=message):
        parse_allotments(read_table(content), HOSPITALS)


def test_xlsx_first_sheet_is_read():
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(["facility_id", "dengue_beds", "non_dengue_beds", "holding_spaces"])
    sheet.append(["HOSP-615", 7, 13, 2])
    buffer = io.BytesIO()
    book.save(buffer)
    result = parse_allotments(read_table(buffer.getvalue()), HOSPITALS)
    assert result["allotments"][0] | {"name": None} == {"facilityId": "HOSP-615", "name": None, "dengueBeds": 7, "nonDengueBeds": 13, "holdingSpaces": 2}


def test_per_hospital_share_overrides_the_scenario_share_in_patient_flow():
    facilities = [{"facilityId": "A", "normalCapacity": 20, "surgeCapacity": 0, "holdingCapacity": 0, "baselineOccupancy": .5},
                  {"facilityId": "B", "normalCapacity": 20, "surgeCapacity": 0, "holdingCapacity": 0, "baselineOccupancy": None}]
    day = simulate_flow([70, 0, 0, 0], facilities, 1, 30, .75)[1]
    a, b = day["facilities"]
    assert a["assumedNonDengueCensus"] == 10 and b["assumedNonDengueCensus"] == 15
    with pytest.raises(ValueError):
        simulate_flow([1, 0, 0, 0], [{**facilities[0], "baselineOccupancy": 1.5}], 1, 4, .75)


@pytest.fixture(scope="module")
def controls():
    return default_workspace()["controlValues"]


def test_qc_simulation_applies_imported_allotments_and_keeps_defaults_elsewhere(controls):
    client = TestClient(app)
    allotment = {"facilityId": "HOSP-614", "dengueBeds": 30, "nonDengueBeds": 10, "holdingSpaces": 7}
    response = client.post("/v1/qc-simulation", json={**controls, "endDate": "2025-02-05", "bedAllotments": [allotment]})
    assert response.status_code == 200, response.text
    data = response.json()
    facilities = {f["facilityId"]: f for f in data["days"][1]["facilities"]}
    assert facilities["HOSP-614"]["normalCapacity"] == 40 and facilities["HOSP-614"]["assumedNonDengueCensus"] == 10
    other = facilities["HOSP-615"]
    assert other["normalCapacity"] == controls["normalCapacity"]
    assert other["assumedNonDengueCensus"] == controls["normalCapacity"] * controls["baselineOccupancy"]
    holding = {f["facilityId"]: f["holdingCapacity"] for f in data["parameters"]["facilities"]}
    assert holding["HOSP-614"] == 7 and holding["HOSP-615"] == controls["holdingCapacity"]
    assert data["controlValues"]["bedAllotments"] == [{**allotment, "extraDengueBeds": None, "extraNonDengueBeds": None, "nonDengueHoldingSpaces": None}]
    assert facilities["HOSP-614"]["bedForecast"]["assumedSupportedDengueCapacity"] == 30


@pytest.mark.parametrize("allotments", [
    [{"facilityId": "HOSP-999", "dengueBeds": 1, "nonDengueBeds": 1, "holdingSpaces": 0}],
    [{"facilityId": "HOSP-614", "dengueBeds": 0, "nonDengueBeds": 0, "holdingSpaces": 0}],
    [{"facilityId": "HOSP-614", "dengueBeds": 1.5, "nonDengueBeds": 1, "holdingSpaces": 0}],
    [{"facilityId": "HOSP-614", "dengueBeds": 1, "nonDengueBeds": 1, "holdingSpaces": 0}] * 2,
], ids=["unknown-hospital", "no-beds", "fractional", "duplicate"])
def test_invalid_allotments_are_rejected_not_repaired(controls, allotments):
    response = TestClient(app).post("/v1/qc-simulation", json={**controls, "endDate": "2025-02-05", "bedAllotments": allotments})
    assert response.status_code == 422, response.text


def test_parse_endpoint_matches_the_approved_hospitals():
    client = TestClient(app)
    response = client.post("/v1/qc-simulation/bed-allotments", content=b"facility_id,dengue_beds,non_dengue_beds,holding_spaces\nHOSP-614,5,15,3\nHOSP-001,1,1,1\n",
                           headers={"content-type": "application/octet-stream"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["hospitalCount"] == 46 and data["measurementKind"] == "assumption"
    assert [a["facilityId"] for a in data["allotments"]] == ["HOSP-614"] and data["errors"][0]["row"] == 3
    assert len(data["hospitalsNotInFile"]) == 45
    bad = client.post("/v1/qc-simulation/bed-allotments", content=b"just,some\ntext,here\n")
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "ALLOTMENT_FILE_INVALID"


def test_optional_extra_bed_columns_are_parsed_and_blank_keeps_default():
    result = parse("facility_id,dengue_beds,non_dengue_beds,holding_spaces,extra_dengue_beds,extra_non_dengue_beds\n"
                   "HOSP-614,5,15,3,6,4\nHOSP-615,5,15,3,,\n")
    first, second = result["allotments"]
    assert first["extraDengueBeds"] == 6 and first["extraNonDengueBeds"] == 4
    assert "extraDengueBeds" not in second and "extraNonDengueBeds" not in second


def test_extra_non_dengue_beds_add_capacity_but_no_dengue_room():
    base = {"facilityId": "A", "normalCapacity": 20, "surgeCapacity": 6, "holdingCapacity": 0, "baselineOccupancy": None}
    plain = simulate_flow([70, 0, 0, 0], [base], 1, 30, .75)
    extra = simulate_flow([70, 0, 0, 0], [{**base, "surgeNonDengueCapacity": 4}], 1, 30, .75)
    a, b = plain[3]["facilities"][0], extra[3]["facilities"][0]
    assert b["supportedCapacity"] == a["supportedCapacity"] + 4 and b["activatedNonDengueSurgeCapacity"] == 4
    assert b["assumedNonDengueCensus"] == a["assumedNonDengueCensus"] + 4
    assert b["supportedCensus"] == a["supportedCensus"] and plain[-1]["cumulativeUnresolved"] == extra[-1]["cumulativeUnresolved"]


def test_qc_simulation_applies_per_hospital_extra_beds(controls):
    allotment = {"facilityId": "HOSP-614", "dengueBeds": 5, "nonDengueBeds": 15, "holdingSpaces": 5, "extraDengueBeds": 9, "extraNonDengueBeds": 3}
    response = TestClient(app).post("/v1/qc-simulation", json={**controls, "endDate": "2025-02-05", "bedAllotments": [allotment]})
    assert response.status_code == 200, response.text
    data = response.json()
    config = {f["facilityId"]: f for f in data["parameters"]["facilities"]}
    assert config["HOSP-614"]["surgeCapacity"] == 9 and config["HOSP-614"]["surgeNonDengueCapacity"] == 3
    assert config["HOSP-615"]["surgeCapacity"] == controls["surgeCapacity"] and config["HOSP-615"]["surgeNonDengueCapacity"] == 0


def test_holding_split_columns_are_parsed_and_must_add_up():
    result = parse("facility_id,dengue_beds,non_dengue_beds,holding_spaces,dengue_holding_spaces,non_dengue_holding_spaces\n"
                   "HOSP-614,5,15,6,4,2\nHOSP-615,5,15,6,4,\nHOSP-616,5,15,6,4,3\n")
    first, second = result["allotments"]
    assert first["nonDengueHoldingSpaces"] == 2 and second["nonDengueHoldingSpaces"] == 2
    assert "dengueHoldingSpaces" not in first
    assert [e["row"] for e in result["errors"]] == [4] and "must equal" in result["errors"][0]["message"]


def test_non_dengue_holding_spaces_are_not_used_for_dengue_overflow(controls):
    allotment = {"facilityId": "HOSP-614", "dengueBeds": 5, "nonDengueBeds": 15, "holdingSpaces": 6, "nonDengueHoldingSpaces": 2}
    client = TestClient(app)
    response = client.post("/v1/qc-simulation", json={**controls, "endDate": "2025-02-05", "bedAllotments": [allotment]})
    assert response.status_code == 200, response.text
    config = {f["facilityId"]: f for f in response.json()["parameters"]["facilities"]}
    assert config["HOSP-614"]["holdingCapacity"] == 4
    too_many = {**allotment, "nonDengueHoldingSpaces": 7}
    assert client.post("/v1/qc-simulation", json={**controls, "endDate": "2025-02-05", "bedAllotments": [too_many]}).status_code == 422
