from app.services.viz import suggest_chart


def test_scalar():
    spec = suggest_chart({"kind": "scalar", "value": 42})
    assert spec["chart"] == "scalar"
    assert spec["data"][0]["value"] == 42


def test_series_categorical_to_bar():
    spec = suggest_chart(
        {"kind": "series", "index": ["LA", "NYC", "SF"], "values": [10, 5, 7]}
    )
    assert spec["chart"] == "bar"
    assert spec["x"] == "name" and spec["y"] == "value"


def test_series_temporal_to_line():
    spec = suggest_chart(
        {"kind": "series", "index": ["2020-01-01", "2020-02-01"], "values": [1, 2]}
    )
    assert spec["chart"] == "line"


def test_series_non_numeric_to_table():
    spec = suggest_chart(
        {"kind": "series", "index": ["a", "b"], "values": ["x", "y"]}
    )
    assert spec["chart"] == "table"


def test_dataframe_two_cols_bar():
    spec = suggest_chart(
        {
            "kind": "dataframe",
            "columns": ["city", "n"],
            "data": [{"city": "LA", "n": 3}, {"city": "NYC", "n": 2},
                     {"city": "SF", "n": 1}],
        }
    )
    assert spec["chart"] == "bar"
    assert spec["x"] == "city" and spec["y"] == "n"


def test_dataframe_two_numeric_scatter():
    spec = suggest_chart(
        {
            "kind": "dataframe",
            "columns": ["age", "income"],
            "data": [{"age": 20, "income": 5}, {"age": 30, "income": 8},
                     {"age": 40, "income": 12}],
        }
    )
    assert spec["chart"] == "scatter"


def test_dataframe_time_series_line():
    spec = suggest_chart(
        {
            "kind": "dataframe",
            "columns": ["month", "revenue"],
            "data": [{"month": "2020-01", "revenue": 100},
                     {"month": "2020-02", "revenue": 120},
                     {"month": "2020-03", "revenue": 140}],
        }
    )
    assert spec["chart"] == "line"


def test_dataframe_single_row_table():
    spec = suggest_chart(
        {"kind": "dataframe", "columns": ["a", "b"], "data": [{"a": 1, "b": 2}]}
    )
    assert spec["chart"] == "table"


def test_dataframe_many_columns_table():
    spec = suggest_chart(
        {
            "kind": "dataframe",
            "columns": ["a", "b", "c"],
            "data": [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}],
        }
    )
    assert spec["chart"] == "table"
