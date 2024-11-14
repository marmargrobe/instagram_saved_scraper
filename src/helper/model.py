from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Boolean, ARRAY, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv
import os

# Initialize Base for ORM class declarations
load_dotenv()

HOST=os.getenv("DB_HOST")
PORT=int(os.getenv("DB_PORT"))
DBNAME=os.getenv("DB_NAME")
USERNAME=os.getenv("DB_USER")
PASSWORD=os.getenv("DB_PASSWORD")

Base = declarative_base()

# Define your database connection URI
DATABASE_URI = f'postgresql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DBNAME}'
engine = create_engine(DATABASE_URI)

# Define the class
class RawstdInstaSavedCollection(Base):
    __tablename__ = 'insta_saved_collections'  # Table name in your database
    __table_args__ = {'schema': 'rawstd'} 

    # Define columns
    id = Column(String, primary_key=True)  # Primary key
    name =  Column(String(50))
    media_count = Column(Integer)
    last_updated = Column(DateTime)


# Define the class
class RawstdInstaSavedReel(Base):
    __tablename__ = 'insta_saved_reels'  # Table name in your database
    __table_args__ = {'schema': 'rawstd'}  # Specify the schema name here
    
    # Define columns
    id = Column(String, primary_key=True)  # Primary key
    pk = Column(String(50))
    code = Column(String)
    taken_at = Column(DateTime)
    media_type = Column(String)
    image_versions2 = Column(JSON)
    product_type = Column(String)
    thumbnail_url = Column(String)
    location = Column(JSON)
    user = Column(JSON)
    comment_count = Column(Integer)
    comments_disabled = Column(Boolean)
    commenting_disabled_for_viewer = Column(Boolean)
    like_count = Column(Integer)
    play_count = Column(Integer)
    has_liked = Column(Boolean)
    caption_text = Column(String)
    accessibility_caption = Column(String)
    usertags = Column(JSON)
    sponsor_tags = Column(JSON)
    video_url = Column(String)
    view_count = Column(Integer)
    video_duration = Column(Float)
    title = Column(String)
    resources = Column(JSON)
    clips_metadata = Column(JSON)
    last_updated = Column(DateTime)


# Define the class
class CleanInstaSavedReel(Base):
    __tablename__ = 'insta_saved_reels'  # Table name in your database
    __table_args__ = {'schema': 'clean'}  # Specify the schema name here
    
    # Define columns
    id = Column(String, primary_key=True)  # Primary key
    pk = Column(String(50))
    code = Column(String)
    taken_at = Column(DateTime)
    media_type = Column(String)
    image_versions2 = Column(JSON)
    product_type = Column(String)
    thumbnail_url = Column(String)
    location = Column(JSON)
    user = Column(JSON)
    comment_count = Column(Integer)
    comments_disabled = Column(Boolean)
    # commenting_disabled_for_viewer = Column(Boolean)
    like_count = Column(Integer)
    play_count = Column(Integer)
    has_liked = Column(Boolean)
    caption_text = Column(String)
    # accessibility_caption = Column(String)
    usertags = Column(JSON)
    sponsor_tags = Column(JSON)
    video_url = Column(String)
    view_count = Column(Integer)
    video_duration = Column(Float)
    # title = Column(String)
    resources = Column(JSON)
    clips_metadata = Column(JSON)
    last_updated = Column(DateTime)
    hashtags = Column(ARRAY(String))
    lng = Column(Float)
    lat = Column(Float)
    city = Column(String)
    location_name = Column(String)
    user_pk = Column(String(50))

class CleanInstaUser(Base):
    __tablename__ = 'insta_user'
    __table_args__ = {'schema': 'clean'}

    id = Column(String(50), primary_key=True)  # Primary key (id)
    username = Column(String(50))  # Instagram username
    full_name = Column(String(100))  # Full name
    profile_pic_url = Column(String)  # Profile picture URL

class CleanInstaUserTag(Base):
    __tablename__ = 'insta_usertags'
    __table_args__ = {'schema': 'clean'}

    id = Column(String(50), primary_key=True)
    username = Column(String(50))
    full_name = Column(String(100))
    profile_pic_url = Column(String)
    tagged_by_insta_user_id = Column(String(50), ForeignKey('clean.insta_user.id'))
    insta_saved_reels_id = Column(String(50), ForeignKey('clean.insta_saved_reels.id'))

    # # Define relationships (optional but useful for accessing related data)
    # tagged_by_insta_user = relationship('CleanInstaUser', backref='usertags')
    # insta_saved_reel = relationship('CleanInstaSavedReel', backref='usertags')

# Define the CleanInstaSavedReelsCategories table
class CleanInstaSavedReelsCategories(Base):
    __tablename__ = "insta_saved_reels_categories"
    __table_args__ = {'schema': 'clean'}  # Specify the schema name here


    id = Column(String(50), primary_key=True, nullable=False)
    processor_category = Column(ARRAY(String), nullable=False)
    processor_version = Column(String(20), nullable=False)
    processor_input = Column(JSON, nullable=False)
    last_updated = Column(DateTime, nullable=True)
# Create tables if they don't exist
Base.metadata.create_all(engine)
