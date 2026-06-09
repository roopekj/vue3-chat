from langchain_core.tools import tool


@tool
def count_rs(text: str) -> str:
    """Count how many times the letter 'r' appears in the given text.

    Use this whenever the user asks how many r's (or R's) are in a word or string.
    """
    n = text.lower().count("r")
    plural = "" if n == 1 else "'s"
    return f"There are {n} r{plural} in {text!r}."


TOOLS = [count_rs]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
