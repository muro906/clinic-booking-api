import unicodedata
import re
import phonenumbers


def normalize_name(raw_str: str) -> str:
    norm = unicodedata.normalize("NFKC", raw_str)
    norm = norm.casefold()
    norm = norm.replace("’", "'")
    norm = re.sub(r"[^\w\s'-]", "", norm)
    norm = " ".join(norm.split())
    if not any(ch.isalpha() for ch in norm):
        raise ValueError("Name must contain at least one valid letter")
    if any(ch.isdigit() or ch == "_" for ch in norm):
        raise ValueError("Names can only be letters,spaces, hypens and apostrophes")
    return norm


def normalize_phone(raw_phone: str) -> str:
    try:
        norm = phonenumbers.parse(raw_phone, "KE")
        

    except phonenumbers.NumberParseException as e:
        raise ValueError("Phone must be a valid kenyan number, for example 0712345678") from e
    if not phonenumbers.is_valid_number_for_region(norm, "KE"):
        raise ValueError("Phone must be a valid kenyan number, for example 0712345678")
    
    return phonenumbers.format_number(norm,phonenumbers.PhoneNumberFormat.E164)
        
    