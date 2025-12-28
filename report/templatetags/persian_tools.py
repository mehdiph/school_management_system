from django import template
import arabic_reshaper
from bidi.algorithm import get_display

register = template.Library()

# Configure reshaper for better compatibility
configuration = {
    'delete_harakat': False,
    'support_ligatures': True,
    'RIAL SIGN': True,
}
reshaper = arabic_reshaper.ArabicReshaper(configuration)

@register.filter(name='reshape')
def reshape_persian_text(text):
    if text is None:
        return ""
    try:
        if not isinstance(text, str):
            text = str(text)
        
        text = text.strip()
        
        # Check if text is actually empty after strip
        if not text:
            return ""

        reshaped_text = reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception as e:
        # Fallback to original text if something goes wrong
        return str(text) if text else ""
