_SENSITIVE_KEYS = {"password", "token", "api_key", "secret", "apikey", "access_token", "client_secret", "private_key", "credentials"}

def redact_sensitive_data(data: dict, extra_sensitive_keys: set = {}) -> dict:
    """
    Redacts sensitive data from a dictionary by replacing the values of specified keys with a placeholder.

    :param data: The original dictionary containing data.
    :return: A new dictionary with sensitive data redacted.
    """

    if extra_sensitive_keys:
        _SENSITIVE_KEYS.update(extra_sensitive_keys)

    redacted_data = {}
    for key, value in data.items():
        if key in _SENSITIVE_KEYS:
            redacted_data[key] = "[REDACTED]"
        else:
            redacted_data[key] = value
    return redacted_data