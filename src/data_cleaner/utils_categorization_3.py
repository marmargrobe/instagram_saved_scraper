from sqlalchemy.orm import sessionmaker, Session
from transformers import pipeline
from datetime import datetime
import numpy as np
from sqlalchemy import update

class DataProcessor:
    __version__ = "1.0.1"  # Version number of the DataProcessor class

    def __init__(self, table_class, engine, batch_size=100, categories=[]):
        """
        Initialize the DataProcessor with a SQLAlchemy table, session, batch size, and classifier.

        Parameters:
        - table_class: The SQLAlchemy ORM model class of the table.
        - engine: The SQLAlchemy database engine.
        - batch_size: Number of records to process at once in batch mode.
        - categories: List of categories for zero-shot classification.
        """
        self.table_class = table_class
        self.engine = engine
        self.batch_size = batch_size
        self.classifier = pipeline("zero-shot-classification")
        self.categories = categories

        # Define columns for additional metadata
        self.keep_columns = ["id", "processor_category", "processor_version", "processor_input", "last_updated"]

        # Create a session factory
        self.Session = sessionmaker(bind=self.engine)

    def categorize_record_zero_shot(self, content):
        """
        Classify content using the zero-shot classifier.

        Parameters:
        - content: The text content to classify.

        Returns:
        - The top category or "Uncategorized" if the content is empty.
        """
        if not content or (isinstance(content, float) and np.isnan(content)):
            return "Uncategorized"
        
        result = self.classifier(content, candidate_labels=self.categories)
        return result['labels'][0]  # Get the most probable category

    def process_record(self, record, lookup_col):
        """
        Process a single SQLAlchemy ORM object using specified lookup columns.

        Parameters:
        - record: A SQLAlchemy ORM object representing a row in the table.
        - lookup_col: The column(s) to retrieve data from for processing.

        Returns:
        - Processed result (e.g., a category) or "Unknown Category" if empty.
        """
        if isinstance(lookup_col, list):
            content = " ".join(
                str(getattr(record, col, "")) for col in lookup_col if getattr(record, col, None) is not None
            ).strip()
        else:
            content = getattr(record, lookup_col, None)

        if not content or (isinstance(content, float) and np.isnan(content)):
            return "Unknown Category"
        
        if isinstance(content, str):
            return self.categorize_record_zero_shot(content)
        
        return "Unknown Category"

    def process_full(self, lookup_col):
        """
        Process all records in the table at once, updating metadata columns in the table.

        Parameters:
        - lookup_col: The column(s) to look up for processing.

        Returns:
        - None (updates are committed to the database directly).
        """
        session = self.Session()
        last_updated_time = datetime.now()
        method_name = f"{self.__class__.__name__}.{self.process_full.__name__}"
        
        # Retrieve all records
        records = session.query(self.table_class).all()

        for record in records:
            category = self.process_record(record, lookup_col)
            record.processor_category = category
            record.processor_version = self.__version__
            record.processor_input = {"method": method_name, "lookup_cols": lookup_col, "categories": self.categories}
            record.last_updated = last_updated_time

        session.commit()
        session.close()

    def process_in_batches(self, lookup_col):
        """
        Process the dataset in batches and add results to metadata columns in the table.

        Parameters:
        - lookup_col: The column(s) to look up for processing.

        Returns:
        - None (updates are committed to the database directly).
        """
        session = self.Session()
        last_updated_time = datetime.now()
        method_name = f"{self.__class__.__name__}.{self.process_in_batches.__name__}"
        
        offset = 0
        while True:
            # Query a batch of records
            batch = session.query(self.table_class).offset(offset).limit(self.batch_size).all()
            if not batch:
                break  # Exit if there are no more records
            
            for record in batch:
                category = self.process_record(record, lookup_col)
                record.processor_category = category
                record.processor_version = self.__version__
                record.processor_input = {"method": method_name, "lookup_cols": lookup_col, "categories": self.categories}
                record.last_updated = last_updated_time

            session.commit()
            offset += self.batch_size

        session.close()
    
    def save_to_csv(self, filename):
        """
        Save all records to a CSV file with their processed columns.

        Parameters:
        - filename: The name of the file to save.
        """
        session = self.Session()
        data = session.query(self.table_class).all()
        
        # Extract rows as dictionaries
        data_dicts = [
            {col: getattr(record, col) for col in self.keep_columns} 
            for record in data
        ]

        # Convert to DataFrame and save to CSV
        df = pd.DataFrame(data_dicts)
        df.to_csv(filename, index=False)
        session.close()
        print(f"Data saved to {filename}")
