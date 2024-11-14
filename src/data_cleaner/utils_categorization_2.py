import pandas as pd
import numpy as np
from transformers import pipeline
from sqlalchemy.orm import sessionmaker
from datetime import datetime



class DataProcessor:
    __version__ = "1.0.1"  # Version number of the DataProcessor class

    def __init__(self, data, batch_size=100, categories=[]):
        """
        Initialize the DataProcessor with data, batch size, and zero-shot classifier.

        Parameters:
        - data: The dataset to process (e.g., a DataFrame).
        - batch_size: Number of records to process at once in batch mode.
        - categories: List of categories for zero-shot classification.
        """
        self.data = data
        self.batch_size = batch_size
        self.classifier = pipeline("zero-shot-classification")
        self.categories = categories
        self.keep_columns = ["id", "processor_category", "processor_version", "processor_input", "last_updated"]

    def categorize_record_zero_shot(self, record):
        """
        Classify the record using the zero-shot classifier.

        Parameters:
        - record: The content to classify.

        Returns:
        - The top category or "Uncategorized" if the record is empty.
        """
        if pd.isna(record) or record == "":
            return "Uncategorized"
        
        result = self.classifier(record, candidate_labels=self.categories)
        return result['labels'][0]  # Get the most probable category

    def process_record(self, record, lookup_col):
        """
        Process a single record using specified lookup columns.

        Parameters:
        - record: A single row from the DataFrame.
        - lookup_col: The column(s) from which to retrieve data to process.

        Returns:
        - Processed result (e.g., a category) or "Unknown Category" if empty.
        """
        # Combine content from specified lookup columns if it's a list, otherwise retrieve single column
        if isinstance(lookup_col, list):
            content = " ".join(
                str(record.get(col, "")) for col in lookup_col if record.get(col, "") is not None
            ).strip()
        else:
            content = record.get(lookup_col, None)

        # Check for empty content
        if not content or (isinstance(content, float) and np.isnan(content)):
            return "Unknown Category"
        
        # Use zero-shot classification if the content is a string
        if isinstance(content, str):
            return self.categorize_record_zero_shot(content)
        
        return "Unknown Category"

    def process_full(self, lookup_col):
        """
        Process the entire dataset at once and add results to the destination column.

        Parameters:
        - lookup_col: The column(s) to look up for processing.

        Returns:
        - DataFrame with the original data and an added destination column.
        """
        # computed_category 
        # computed_category_code_version
        # computed_category_inputs
        last_updated_time = datetime.now()

        method_name = f"{self.__class__.__name__}.{self.process_full.__name__}"
        print(method_name)
        print(self.data)
        self.data["processor_category"] = self.data.apply(lambda record: self.process_record(record, lookup_col), axis=1)
        self.data["processor_version"] = self.__version__
        self.data["processor_input"] = {"method": method_name, "lookup_cols": lookup_col, "categories": self.categories}
        self.data["last_updated"] = last_updated_time
            
        return self.data[self.keep_columns]

    def process_in_batches(self, lookup_col):
        """
        Process the dataset in batches and add results to the destination column.

        Parameters:
        - lookup_col: The column(s) to look up for processing.

        Returns:
        - DataFrame with the original data and an added destination column.
        """
        last_updated_time = datetime.now()

        method_name = f"{self.__class__.__name__}.{self.process_in_batches.__name__}"

        results = []
        
        for start in range(0, len(self.data), self.batch_size):
            batch = self.data.iloc[start:start + self.batch_size].copy()
            batch["processor_category"] = batch.apply(lambda record: self.process_record(record, lookup_col), axis=1)
            results.append(batch)
        all_results = pd.concat(results, ignore_index=True)
        all_results["processor_version"] = self.__version__
        all_results["processor_input"] = {"method": method_name, "lookup_cols": lookup_col, "categories": self.categories}
        all_results["last_updated"] = last_updated_time
        return all_results[self.keep_columns]
    
    def save_to_csv(self, filename):
        """
        Save the processed DataFrame to a CSV file.

        Parameters:
        - filename: The name of the file to save the DataFrame.
        """
        self.data.to_csv(filename, index=False)
        print(f"Data saved to {filename}")

## CHANGE
# Option 1: transactional db tables with columns:
# computed_category 
# computed_category_code_version
# computed_category_inputs

# Option 2: separate db tables for each computation

