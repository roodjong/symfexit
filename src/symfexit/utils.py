def enable_if(condition, value, otherwise=None):
    if otherwise is None:
        otherwise = []
    if isinstance(condition, str) and (
        condition.lower() == "false" or condition == "0"
    ):
        condition = False
    if condition and callable(value):
        value = value()
    elif condition:
        value = value
    elif callable(otherwise):
        value = otherwise()
    else:
        value = otherwise
    return value
