import pandas as pd
import json

reels_column_dtype = {
    'pk': "str",  # Convert pk to string
    'id': "str",  # Convert id to string
    'code': "str",  # Convert code to string
    'taken_at': "timestamp",  # Convert to datetime with error handling
    'media_type': "str",  # Convert to string

    'image_versions2': "jsonb",  # Convert to JSON string or None
    
    'product_type': "str",  # Convert to string
    'thumbnail_url': "str",  # Convert to string

    'location': "jsonb",  # Convert to JSON string or None

    'user': "jsonb",  # Convert to JSON string or None

    'comment_count': "int",  # Convert to integer, allowing NaN
    'comments_disabled': "bool",  # Convert to boolean
    'commenting_disabled_for_viewer': "bool",  # Convert to boolean
    'like_count': "int",  # Convert to integer, allowing NaN
    'play_count': "int",  # Convert to integer, allowing NaN
    'has_liked': "bool",  # Convert to boolean
    'caption_text': "str",  # Convert to string
    'accessibility_caption': "float",  # Convert to float

    'usertags': "jsonb",  # Convert to JSON string or None

    'sponsor_tags': "jsonb",  # Convert to JSON string or None

    'video_url': "str",  # Convert to string
    'view_count': "int",  # Convert to integer, allowing NaN
    'video_duration': "float",  # Convert to float
    'title': "str",  # Convert to string, keeping None as NaN

    'resources': "jsonb",  # Convert to JSON string or None
    'clips_metadata': "jsonb",  # Convert to JSON string or None

    'last_updated': "timestamp"  # Convert to datetime with error handling
}

# Define the column transformations in a dictionary for efficiency
reels_column_transformations = {
    'pk': str,  # Convert pk to string
    'id': str,  # Convert id to string
    'code': str,  # Convert code to string
    'taken_at': lambda x: pd.to_datetime(x, errors='coerce'),  # Convert to datetime with error handling
    'media_type': str,  # Convert to string

    'image_versions2': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None
    
    'product_type': str,  # Convert to string
    'thumbnail_url': str,  # Convert to string

    'location': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None

    'user': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None

    'comment_count': lambda x: pd.to_numeric(x, errors='coerce', downcast='integer'),  # Convert to integer, allowing NaN
    'comments_disabled': bool,  # Convert to boolean
    'commenting_disabled_for_viewer': bool,  # Convert to boolean
    'like_count': lambda x: pd.to_numeric(x, errors='coerce', downcast='integer'),  # Convert to integer, allowing NaN
    'play_count': lambda x: pd.to_numeric(x, errors='coerce', downcast='integer'),  # Convert to integer, allowing NaN
    'has_liked': bool,  # Convert to boolean
    'caption_text': str,  # Convert to string
    'accessibility_caption': float,  # Convert to float

    'usertags': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None

    'sponsor_tags': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None

    'video_url': str,  # Convert to string
    'view_count': lambda x: pd.to_numeric(x, errors='coerce', downcast='integer'),  # Convert to integer, allowing NaN
    'video_duration': float,  # Convert to float
    'title': lambda x: x if pd.isna(x) else str(x),  # Convert to string, keeping None as NaN

    'resources': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None
    'clips_metadata': lambda x: json.dumps(str(x)) if x is not None else None,  # Convert to JSON string or None

    'last_updated': lambda x: pd.to_datetime(x, errors='coerce')  # Convert to datetime with error handling
}

def transform_dtypes(df, column_transformations, column_dtypes):
    # Apply transformations based on the dictionary

    # Replace all NaN values with None to avoid issues with inserting NULLs into the database
    df = df.where(pd.notnull(df), None)

    for column, transform in column_transformations.items():
        column_dtype = column_dtypes[column]
        
        if column in df.columns:
            if "jsonb" == column_dtype:
                df[column] = df[column].apply(lambda x: str(x).replace("None", "null") if x is not None else None)
            # Apply the transformation function or cast type
            if callable(transform):
                df[column] = df[column].apply(transform)
            else:
                df[column] = df[column].astype(transform)
            if "jsonb" == column_dtype:
                df[column] = df[column].apply(lambda x: str(x).replace("False", "false") if x is not None else None)
                df[column] = df[column].apply(lambda x: str(x).replace("True", "true") if x is not None else None)


    
    return df

# Now df has the correct dtypes for the PostgreSQL table
