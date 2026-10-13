import pandas as pd
import ast
import io
import re
import tokenize

# transform_dtypes turns None/True/False into null/true/false, and instagrapi writes
# URLs as HttpUrl('...', ); map those back so the text parses as a Python literal
_LITERAL_NAMES = {"null": "None", "true": "True", "false": "False"}
_URL_WRAPPER = re.compile(r"""\b(?:Http)?Url\(\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\s*,?\s*\)""")


def _to_python_literal(object_str):
    object_str = _URL_WRAPPER.sub(r"\1", object_str)
    tokens = []
    for tok in tokenize.generate_tokens(io.StringIO(object_str).readline):
        if tok.type == tokenize.NAME and tok.string in _LITERAL_NAMES:
            tok = tok._replace(string=_LITERAL_NAMES[tok.string])
        tokens.append((tok.type, tok.string))
    return tokenize.untokenize(tokens)


# Function to safely convert the location string into a dictionary
def parse_dict_object(object_str):
    if object_str is None or (not isinstance(object_str, str) and pd.isna(object_str)):  # Handle NaN values
        return {}
    if isinstance(object_str, (dict, list)):
        return object_str
    try:
        # Use ast.literal_eval to safely parse the string into a dictionary
        return ast.literal_eval(_to_python_literal(object_str))
    except (ValueError, SyntaxError, tokenize.TokenError):
        # In case the location format is unexpected, return an empty dictionary
        return {}

# Function to extract specific information (e.g., city) from the location dictionary
def extract_key(dict_value, key):
    # Access the 'city' key in the location dictionary
    return dict_value.get(key, None)

# Function to extract hashtags
def extract_hashtags(text):
    # Ensure the text is a string (convert NaN or non-string to an empty string)
    if isinstance(text, str):
        hashtags = re.findall(r'#(\w+)', text)  # Capture the word after '#'
        return hashtags
    else:
        return []  # Return an empty list for non-string values

# Define a function to extract a specific key from a dictionary
def extract_key(obj, key):
    return obj.get(key) if isinstance(obj, dict) else None

# # Define a function to parse the 'user' field if it's a JSON-like string or dict
# def parse_dict_object(user):
#     if isinstance(user, str):
#         try:
#             return json.loads(user)
#         except json.JSONDecodeError:
#             return None
#     elif isinstance(user, dict):
#         return user
#     return None


# check if caption_text has GPE
# create list with locations_from_caption

def extract_location_from_caption(text, nlp):
    doc = nlp(text)
    location_list = []
    for entity in doc.ents:
        if entity.label_ == 'GPE':
            location_list.append(entity.text)
    return location_list