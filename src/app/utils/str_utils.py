import logging

logger = logging.getLogger(__name__)

def clean_string(s):
    translation_table = str.maketrans(
        'áàâãäéèêëíìîïóòôõöúùûüç',
        'aaaaaeeeeiiiiooooouuuuc'
    )
    cleaned = ' '.join(s.lower().translate(translation_table).replace('-', '').split())
    logger.debug(f"Cleaned string: Original: {s}, Cleaned: {cleaned}")
    return cleaned