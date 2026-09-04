"""Layer 1 of the sandbox: static AST rules. See SECURITY.md.

These run in-process with no subprocess, so the whole escape suite is cheap
enough to keep expanding as new tricks turn up.
"""
import pytest

from app.services.code_guard import CodeRejected, check, validate

# Each of these ran successfully against the pre-hardening sandbox. `A` reached
# the real `__builtins__` (arbitrary code execution); `B`/`C` read and wrote
# arbitrary files through pandas without using a single dunder.
ESCAPES = {
    "subclasses_to_builtins": (
        "cls = ().__class__.__base__.__subclasses__()\n"
        "cat = [c for c in cls if c.__name__ == 'catch_warnings'][0]\n"
        "result = str(cat()._module.__builtins__)\n"
    ),
    "pandas_writes_a_file": "df.to_csv('/tmp/pwned.txt')\nresult = 1",
    "pandas_reads_a_file": "result = pd.read_csv('/etc/passwd').shape",
    "getattr_with_built_string": "result = getattr(df, '__cla' + 'ss__')",
    "private_attribute_hop": "result = df._mgr",
    "import_os": "import os\nresult = os.listdir('.')",
    "import_from": "from os import listdir\nresult = listdir('.')",
    "dunder_import": "result = __import__('os').getcwd()",
    "builtins_by_name": "result = __builtins__",
    "df_query_evaluates_strings": "result = df.query('age > 1')",
    "df_eval_evaluates_strings": "result = df.eval('age * 2')",
    "open_a_file": "result = open('secret.txt').read()",
    "eval_call": "result = eval('1+1')",
    "exec_call": "exec('x = 1')\nresult = 1",
    "compile_call": "result = compile('1', '<s>', 'eval')",
    "walk_the_mro": "result = df.mro()",
    "jinja_via_styler": "result = df.style",
    "to_pickle": "result = df.to_pickle('x.pkl')",
    "to_sql": "result = df.to_sql('t', 'sqlite://')",
    "globals_call": "result = globals()",
    "vars_call": "result = vars(df)",
    # `str.format` is the interpreter's own string-driven getattr: the whole
    # traversal sits inside a literal, so there is no ast.Attribute to reject.
    # Against the pre-fix guard this one returned the sandbox's entire
    # os.environ -- GEMINI_API_KEY, JWT_SECRET and AWS keys included.
    "format_walks_to_os_environ": (
        'result = "{0.__class__.__init__.__globals__[sys].modules[os].environ}"'
        ".format(df)"
    ),
    "format_reaches_builtins": (
        'result = "{0.__class__.__init__.__globals__[__builtins__]}".format(df)'
    ),
    "format_map_does_the_same": 'result = "{0.__class__}".format_map({0: df})',
}

# Ordinary analysis code the LLM actually writes. A guard that blocks these is
# useless, so they are as important as the escape cases above.
LEGITIMATE = {
    "mean": "result = df['age'].mean()",
    "groupby": "result = df.groupby('city').size().reset_index(name='n')",
    "underscore_loop_var": "t = 0\nfor _, row in df.iterrows():\n    t += row['age']\nresult = t",
    "to_datetime_is_not_a_writer": "result = pd.to_datetime(df['d']).dt.year",
    "to_dict_to_numpy_to_list": "result = df.to_dict(orient='records')",
    "lambda_and_assign": "result = df.assign(x=lambda d: d['age'] * 2)['x'].sum()",
    "chained_pandas": "result = df.sort_values('age').head(10).reset_index(drop=True)",
    "pivot_table": "result = pd.pivot_table(df, index='city', values='age', aggfunc='mean')",
    "str_accessor": "result = df['city'].str.upper().value_counts()",
    "conditional": "result = df[df['age'] > 30]['city'].nunique() if len(df) else 0",
    "try_except": "try:\n    result = df['age'].sum()\nexcept Exception:\n    result = 0",
    "comprehension": "result = [c for c in df.columns if c != 'age']",
    "percent_formatting_is_fine": "result = '%d rows' % len(df)",
    "f_string_on_a_value_is_fine": "result = f'{df[\"age\"].mean():.2f}'",
}


@pytest.mark.parametrize("name", sorted(ESCAPES))
def test_escape_is_rejected(name):
    with pytest.raises(CodeRejected):
        validate(ESCAPES[name])


@pytest.mark.parametrize("name", sorted(LEGITIMATE))
def test_legitimate_code_is_allowed(name):
    validate(LEGITIMATE[name])  # must not raise


def test_string_tricks_cannot_defeat_the_rules():
    """The old substring blacklist fell to concatenation; the AST rules do not."""
    for code in (
        "result = getattr(df, '__' + 'class__')",
        "result = df.to_c" "sv('x')",
        "exec('imp' 'ort os')",
    ):
        with pytest.raises(CodeRejected):
            validate(code)


def test_syntax_error_is_reported_not_raised_as_syntaxerror():
    with pytest.raises(CodeRejected) as exc:
        validate("result = df[")
    assert "not valid Python" in str(exc.value)


def test_error_message_names_the_line():
    with pytest.raises(CodeRejected) as exc:
        validate("x = 1\nresult = df.to_csv('a')")
    assert "line 2" in str(exc.value)


def test_check_returns_message_for_the_retry_loop():
    msg = check("import os\nresult = 1")
    assert msg is not None
    assert "rejected by the sandbox" in msg
    # The retry prompt feeds this back to the model, so it must say what to do.
    assert "pandas" in msg


def test_check_returns_none_for_clean_code():
    assert check("result = df['age'].mean()") is None
