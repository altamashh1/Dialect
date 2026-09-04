from app.services.prompt import build_prompt, extract_code

PROFILE = {"n_rows": 3, "columns": {"age": {"type": "integer"}}}


def test_build_prompt_includes_question_and_profile():
    p = build_prompt(PROFILE, "average age?")
    assert "average age?" in p
    assert '"age"' in p
    assert "error" not in p.lower()


def test_build_prompt_with_error_adds_retry_section():
    p = build_prompt(PROFILE, "average age?", error="KeyError: 'Age'")
    assert "KeyError: 'Age'" in p
    assert "failed" in p.lower()


def test_extract_code_from_python_fence():
    text = "Here you go:\n```python\nresult = df['age'].mean()\n```\nDone."
    assert extract_code(text) == "result = df['age'].mean()"


def test_extract_code_from_bare_fence():
    assert extract_code("```\nresult = 1\n```") == "result = 1"


def test_extract_code_falls_back_to_raw():
    assert extract_code("result = df.shape[0]") == "result = df.shape[0]"
