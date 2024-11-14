## Data Processor
"""
This script handles the categorization of the data.
You can use the zero-shot classification logic you already have here, where you pull raw data from the database and categorize it based on your predefined categories.

Kafka consumer:
This will listen to the Kafka topic and when a message is received, it will filter the data in the raw table based on the timestamp and process the new records.
The consumer will then trigger the categorization and send the updated records to the next script for transformation.
"""

## Data Ingestion
"""
This script will read the Instagram data, either from an API or a CSV, and write it to the raw data table in the database.
It could periodically check for new data or use a Kafka consumer to trigger updates.


Kafka producer:
-After ingesting new data into the raw table, the producer sends a Kafka message to trigger processing.
Include the smallest last_updated timestamp or an identifier to inform the consumers of the new data that needs to be processed.

"""