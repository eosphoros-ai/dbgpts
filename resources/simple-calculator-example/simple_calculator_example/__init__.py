"""Simple calculator tool example."""

from dbgpt.agent.resource import tool


@tool
def simple_calculator(first_number: int, second_number: int, operator: str) -> float:
    """Simple calculator tool. Just support +, -, *, /."""
    if operator == "+":
        return first_number + second_number
    elif operator == "-":
        return first_number - second_number
    elif operator == "*":
        return first_number * second_number
    elif operator == "/":
        return first_number / second_number
    else:
        raise ValueError(f"Invalid operator: {operator}")
