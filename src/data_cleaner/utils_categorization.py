from sqlalchemy.orm import Session
from transformers import pipeline
from datetime import datetime
import numpy as np
from src.helper.model import CleanInstaSavedReelsCategories, CleanInstaSavedReel, RawstdInstaSavedCollection
import pandas as pd

from sqlalchemy.orm import Session
from datetime import datetime
from transformers import pipeline

class DataProcessor:
    __version__ = "1.0.6"  # Version number of the DataProcessor class

    def __init__(self, session: Session, categories=[], number_of_categories=3, destination_table_class=CleanInstaSavedReelsCategories, source_table_class=CleanInstaSavedReel):
        """
        Initialize the DataProcessor with a SQLAlchemy session, batch size, and classifier.

        Parameters:
        - session: SQLAlchemy session object.
        - categories: List of categories for zero-shot classification.
        - number_of_categories: # of categories to return. Default set to 3.
        - destination_table_class: SQLAlchemy model class for the destination table.
        - source_table_class: SQLAlchemy model class for the source table.
        """
        self.destination_table_class = destination_table_class
        self.source_table_class = source_table_class
        self.classifier = pipeline("zero-shot-classification")
        self.number_of_categories = number_of_categories
        self.keep_columns = ["id", "processor_category", "processor_version", "processor_input", "last_updated"]
        self.session = session
        self.categories = categories if categories else self._fetch_default_categories()

    def _fetch_default_categories(self):
        """
        Fetch default categories from the rawstd saved collections table if no categories are provided.

        Returns:
        - A list of unique categories for classification.
        """
        rawstd_collections = self.session.query(RawstdInstaSavedCollection).distinct().all()
        return [x.name for x in rawstd_collections]




    def categorize_record_zero_shot(self, content):
        """
        Classify content using the zero-shot classifier and return a list of top categories.
        """
        if not content or (isinstance(content, float) and np.isnan(content)):
            return ["Uncategorized"]

        # If content is a list, join elements into a single string
        if isinstance(content, list):
            content = " ".join(map(str, content))  # Join list items into a single string

        result = self.classifier(content, candidate_labels=self.categories)
        return result['labels'][:self.number_of_categories] if result['labels'] else ["Uncategorized"]

    def process_record(self, record, lookup_col):
        """
        Process a single SQLAlchemy ORM object using specified lookup columns and return a list of categories.
        """
        if isinstance(lookup_col, list):
            content = " ".join(
                str(getattr(record, col, "")) for col in lookup_col if getattr(record, col, None) is not None
            ).strip()
        else:
            content = getattr(record, lookup_col, None)

        # Handle the case where content is a list
        if isinstance(content, list):
            content = " ".join(map(str, content))  # Join list items into a single string

        if isinstance(content, str):
            return self.categorize_record_zero_shot(content)

        return ["Uncategorized"]


    
    def get_records_from_source_table_class(self,):
        # return all records if batch_size is 0
        return self.session.query(self.source_table_class).all()

    def get_records_from_source_table_class_batch(self, offset=0, batch_size=100):
        return self.session.query(self.source_table_class).offset(offset).limit(batch_size).all()


    def process_full(self, lookup_col, insert_into_table=False, insert_type="single"):
        """
        Process all records in the table at once, updating metadata columns in the table.

        param:
        - insert_type: "single" or "bulk"
        """
        print(self.categories)
        insert_single = False
        insert_bulk = False
        if insert_into_table:
            if insert_type == "single":
                insert_single = True
            elif insert_type == "bulk":
                insert_bulk = True
            else:
                raise ValueError(f"Invalid insert_type: {insert_type}. Accepted values are 'single' or 'bulk'.")

        last_updated_time = datetime.now()
        method_name = f"{self.__class__.__name__}.{self.process_full.__name__}"
        
        # Retrieve all records
        records = self.get_records_from_source_table_class()
        processed_data = []
        for record in records:
            current_record = {
                "id": record.id,
                "processor_category": self.process_record(record, lookup_col),
                "processor_version": self.__version__,
                "processor_input": {"method": method_name, "lookup_cols": lookup_col, "categories": self.categories, "number_of_categories": self.number_of_categories},
                "last_updated": last_updated_time
            }
        
            processed_record = self.destination_table_class(**current_record)
            processed_data.append(processed_record)
            if insert_single:
                print(f"inserting single record: {processed_record.id}")
                self.insert_single_record(processed_record)


        if insert_bulk:
            print(f"inserting bulk: {str(len(processed_data))}")

            self.bulk_insert(processed_data)

        self.session.commit()

    def process_in_batches(self, lookup_col, batch_size=100, insert_into_table=False):
        """
        Process the dataset in batches and add results to metadata columns in the table.
        """
        last_updated_time = datetime.now()
        method_name = f"{self.__class__.__name__}.{self.process_in_batches.__name__}"
        
        offset = 0
        processed_data = []
        while True:
            # Query a batch of records
            batch = self.get_records_from_source_table_class_batch(offset=offset,batch_size=batch_size)
            if not batch:
                break  # Exit if there are no more records
            for record in batch:
                current_record = {
                    "id": record.id,
                    "processor_category": self.process_record(record, lookup_col),
                    "processor_version": self.__version__,
                    "processor_input": {"method": method_name, "batch_size": batch_size, "lookup_cols": lookup_col, "categories": self.categories, "number_of_categories": self.number_of_categories},
                    "last_updated": last_updated_time
                }

                processed_record = self.destination_table_class(**current_record)
                processed_data.append(processed_record)

            if insert_into_table:
                self.bulk_insert(processed_data)

            offset += batch_size

        self.session.commit()

    def insert_single_record(self, record):
        """
        Insert a single processed record into the destination table.
        """
        self.session.add(record)
        self.session.commit()

    def bulk_insert(self, processed_data):
        """
        Efficiently inserts a list of data dictionaries into the database using bulk_insert_mappings.
        """
        # Use bulk_insert_mappings for efficiency when inserting many records
        self.session.bulk_insert_mappings(self.destination_table_class, [data.__dict__ for data in processed_data])
        self.session.commit()
