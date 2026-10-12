import argparse
from sqlalchemy.orm import sessionmaker
from src.helper.model import engine
from src.data_cleaner.utils_categorization import DataProcessor

def main(lookup_cols, top_n):
    # Initialize the session factory
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    # Use session in a context manager
    with Session() as session:
        # Initialize DataProcessor with the session and categories
        processor = DataProcessor(session=session, number_of_categories=top_n)
        
        # Process based on the provided lookup_cols (multiple columns are supported)
        processor.process_full(lookup_col=lookup_cols,
                               insert_into_table=True,
                               insert_type="single",
                               specific_version_only='current')

if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Data Categorization Script")
    parser.add_argument(
        "--lookup_col",
        nargs="+",  # allows multiple columns to be passed as arguments
        required=True,
        help="The columns to look up, e.g., 'hashtags', 'caption_text', 'city', etc.",
    )
    parser.add_argument(
        "--top_n",
        type=int,
        default=7,
        help="The number of categories to process (default is 7)."
    )

    # Parse arguments
    args = parser.parse_args()

    # Call main function with parsed arguments
    main(lookup_cols=args.lookup_col, top_n=args.top_n)
