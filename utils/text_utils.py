
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


def sanitize_for_csv(text: str, keep_chars: str = "") -> str:
    """
    Sanitizes text for CSV output.
    Removes newlines and control characters.
    By default, keeps alphanumeric and spaces.
    keep_chars: string of additional characters to preserve (e.g. "/._-").
    """
    if not text:
        return ""
    
    # Remove newlines and tabs
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # If keep_chars is provided, construct regex to keep them
    if keep_chars:
        # Escape keep_chars for regex
        escaped_chars = re.escape(keep_chars)
        pattern = f'[^a-zA-Z0-9\\s{escaped_chars}]'
    else:
        pattern = r'[^a-zA-Z0-9\s]'
        
    cleaned = re.sub(pattern, ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()
