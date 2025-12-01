import re

def clean_text_for_json(text: str) -> str:
    """
    Cleans text to be suitable for JSON storage and analysis.
    Keeps only letters, numbers, and spaces.
    Collapses multiple spaces into one and strips leading/trailing whitespace.
    """
    if not text:
        return ""
    
    # Replace non-alphanumeric characters (excluding spaces) with a space
    # This ensures that words separated by punctuation don't get merged
    # e.g. "hello,world" -> "hello world" instead of "helloworld"
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    
    # Collapse multiple spaces into one
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.strip()
