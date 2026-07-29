from configs.config import settings

def redact_sensitive_data(data: dict, extra_sensitive_keys: set = {}) -> dict:
    """
    Redacts sensitive data from a dictionary by replacing the values of specified keys with a placeholder.

    :param data: The original dictionary containing data.
    :return: A new dictionary with sensitive data redacted.
    """
    
    if not isinstance(data, dict):
        return data
        
    redacted = data.copy()
    for key, value in redacted.items():
        if key.lower() in settings.sensitive_keys:
            redacted[key] = "********"
        elif isinstance(value, dict):
            # Llamada recursiva por si hay diccionarios anidados
            redacted[key] = redact_sensitive_data(value)
            
    return redacted