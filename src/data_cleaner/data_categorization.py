from sqlalchemy.orm import sessionmaker
from src.helper.model import engine, RawstdInstaSavedCollection
from src.data_cleaner.utils_categorization import DataProcessor


option_1 = True
option_2 = False
top_n = 5
if option_1:
    # Initialize the session factory
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    # Set processing flags
    process_hastags = True
    process_caption_text = False
    process_city = False
    process_location_list = False
    process_location_name = False
    process_lng_lat = False
    process_usertags = False

    # Use session in a context manager
    with Session() as session:
        # Initialize DataProcessor with the session and categories
        processor = DataProcessor(session=session, number_of_categories=top_n)

        # Processing logic for each type, based on flags
        if process_hastags:
            lookup_col = 'hashtags'
            processor.process_full(lookup_col=lookup_col, insert_into_table=True, insert_type="single")

        if process_caption_text:
            lookup_col = 'caption_text'
            processor.process_full(lookup_col=lookup_col)

        if process_city:
            lookup_col = 'city'
            processor.process_full(lookup_col=lookup_col)

        if process_location_list:
            lookup_col = ['location_name', 'city', 'lng', 'lat']
            processor.process_full(lookup_col=lookup_col)

        if process_location_name:
            lookup_col = 'location_name'
            processor.process_full(lookup_col=lookup_col)

        if process_lng_lat:
            lookup_col = ['lng', 'lat']
            processor.process_full(lookup_col=lookup_col)

        if process_usertags:
            lookup_col = 'usertags'
            processor.process_full(lookup_col=lookup_col)
elif option_2:
    # Initialize the session factory
    Session = sessionmaker(bind=engine)

    # Set processing flags
    process_hastags = True
    process_caption_text = False
    process_city = False
    process_location_list = False
    process_location_name = False
    process_lng_lat = False
    process_usertags = False

    # Create and manage session manually with try...finally
    session = Session()
    try:
        # Initialize DataProcessor with the session and categories
        processor = DataProcessor(session=session,number_of_categories=top_n)

        # Processing logic for each type, based on flags
        if process_hastags:
            lookup_col = 'hashtags'
            processor.process_full(lookup_col=lookup_col, insert_into_table=True, insert_type="single")

        if process_caption_text:
            lookup_col = 'caption_text'
            processor.process_full(lookup_col=lookup_col)

        if process_city:
            lookup_col = 'city'
            processor.process_full(lookup_col=lookup_col)

        if process_location_list:
            lookup_col = ['location_name', 'city', 'lng', 'lat']
            processor.process_full(lookup_col=lookup_col)

        if process_location_name:
            lookup_col = 'location_name'
            processor.process_full(lookup_col=lookup_col)

        if process_lng_lat:
            lookup_col = ['lng', 'lat']
            processor.process_full(lookup_col=lookup_col)

        if process_usertags:
            lookup_col = 'usertags'
            processor.process_full(lookup_col=lookup_col)

    finally:
        # Ensure the session is closed
        session.close()
