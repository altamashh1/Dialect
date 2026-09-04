from app.services.verify import check_invariants, classify

PROFILE = {"n_rows": 100, "columns": {}}


def scalar(v):
    return {"kind": "scalar", "value": v}


def series(vals):
    return {"kind": "series", "index": list(range(len(vals))), "values": vals}


def test_clean_result_no_issues():
    assert check_invariants(scalar(42), PROFILE, "total revenue") == []


def test_percentage_out_of_range_is_error():
    issues = check_invariants(scalar(140.0), PROFILE, "what percentage returned?")
    assert ("error", ) == tuple(sev for sev, _ in issues)


def test_negative_on_nonneg_measure_warns():
    issues = check_invariants(series([10, -3, 5]), PROFILE, "total sales by region")
    assert any(sev == "warn" and "negative" in msg for sev, msg in issues)


def test_empty_result_warns():
    issues = check_invariants(series([]), PROFILE, "revenue by region")
    assert any("empty" in msg for _s, msg in issues)


def test_count_exceeding_rows_warns():
    issues = check_invariants(scalar(500), PROFILE, "how many orders?")
    assert any("exceeds the dataset row count" in msg for _s, msg in issues)


def test_negative_count_is_error():
    issues = check_invariants(scalar(-1), PROFILE, "how many orders?")
    assert any(sev == "error" for sev, _ in issues)


def test_non_integer_count_warns():
    issues = check_invariants(scalar(3.5), PROFILE, "how many customers?")
    assert any("non-integer" in msg for _s, msg in issues)


def test_classify_matrix():
    assert classify([], "PASS") == "high"
    assert classify([], None) == "medium"
    assert classify([("warn", "x")], "PASS") == "medium"
    assert classify([("error", "x")], "PASS") == "low"
    assert classify([], "FAIL") == "low"
