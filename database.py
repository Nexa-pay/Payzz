from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
from config import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String, nullable=True)
    coins = Column(Integer, default=0)
    is_admin = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)  # Owner's telegram ID
    phone_number = Column(String, unique=True)
    session_string = Column(String)  # Encrypted session
    is_active = Column(Boolean, default=True)
    reports_count = Column(Integer, default=0)
    last_report_time = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    
class Report(Base):
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer)
    target_type = Column(String)  # 'group', 'channel', 'user'
    target_id = Column(String)
    reported_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    
class ReportTarget(Base):
    __tablename__ = 'report_targets'
    
    id = Column(Integer, primary_key=True)
    target_type = Column(String)
    target_id = Column(String)
    target_username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    added_by = Column(Integer)  # Admin ID
    added_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()