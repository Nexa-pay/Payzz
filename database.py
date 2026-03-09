import logging
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Index, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool, NullPool
from contextlib import contextmanager
import json
from config import DATABASE_URL

# Configure logging
logger = logging.getLogger(__name__)

# ============================================
# DATABASE ENGINE CONFIGURATION
# ============================================

# Configure engine based on database type
if 'sqlite' in DATABASE_URL:
    # SQLite specific configuration
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False},
        poolclass=NullPool,  # SQLite doesn't need connection pooling
        echo=False
    )
    logger.info("✅ Using SQLite database")
else:
    # PostgreSQL specific configuration
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
        echo=False
    )
    logger.info("✅ Using PostgreSQL database")

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# Scoped session for thread safety
db_session = scoped_session(SessionLocal)

Base = declarative_base()

# ============================================
# DATABASE MODELS
# ============================================

class User(Base):
    """User model for bot users"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    coins = Column(Integer, default=0, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_owner = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    total_reports = Column(Integer, default=0, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_users_telegram_id', 'telegram_id'),
        Index('idx_users_username', 'username'),
        Index('idx_users_is_admin', 'is_admin'),
        Index('idx_users_coins', 'coins'),
    )
    
    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'telegram_id': self.telegram_id,
            'username': self.username,
            'coins': self.coins,
            'is_admin': self.is_admin,
            'is_owner': self.is_owner,
            'is_banned': self.is_banned,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Account(Base):
    """Telegram account model for reporting accounts"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)  # Owner's telegram ID
    phone_number = Column(String, unique=True, nullable=False, index=True)
    session_string = Column(Text, nullable=False)  # Encrypted session
    api_id = Column(Integer, nullable=True)  # Optional custom API ID for this account
    api_hash = Column(String, nullable=True)  # Optional custom API hash
    is_active = Column(Boolean, default=True, nullable=False)
    is_working = Column(Boolean, default=True, nullable=False)
    reports_count = Column(Integer, default=0, nullable=False)
    successful_reports = Column(Integer, default=0, nullable=False)
    failed_reports = Column(Integer, default=0, nullable=False)
    last_report_time = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_accounts_user_id', 'user_id'),
        Index('idx_accounts_phone', 'phone_number'),
        Index('idx_accounts_active', 'is_active'),
        Index('idx_accounts_cooldown', 'cooldown_until'),
    )
    
    def __repr__(self):
        return f"<Account(phone={self.phone_number}, user_id={self.user_id})>"
    
    @property
    def is_on_cooldown(self):
        """Check if account is on cooldown"""
        if self.cooldown_until and self.cooldown_until > datetime.utcnow():
            return True
        return False
    
    def to_dict(self):
        return {
            'id': self.id,
            'phone_number': self.phone_number,
            'is_active': self.is_active,
            'reports_count': self.reports_count,
            'successful_reports': self.successful_reports,
            'failed_reports': self.failed_reports,
            'last_report_time': self.last_report_time.isoformat() if self.last_report_time else None,
            'is_on_cooldown': self.is_on_cooldown
        }


class Report(Base):
    """Report model for tracking reports"""
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # User who initiated report
    target_type = Column(String, nullable=False)  # 'group', 'channel', 'user'
    target_id = Column(String, nullable=False, index=True)
    target_username = Column(String, nullable=True)
    reason = Column(String, nullable=True)  # Optional report reason
    status = Column(String, default='pending')  # pending, success, failed
    error_message = Column(String, nullable=True)
    reported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_reports_account', 'account_id'),
        Index('idx_reports_target', 'target_id'),
        Index('idx_reports_user', 'user_id'),
        Index('idx_reports_status', 'status'),
        Index('idx_reports_date', 'reported_at'),
    )
    
    def __repr__(self):
        return f"<Report(target={self.target_id}, status={self.status})>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'status': self.status,
            'reported_at': self.reported_at.isoformat() if self.reported_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class ReportTarget(Base):
    """Target model for storing report targets"""
    __tablename__ = 'report_targets'
    
    id = Column(Integer, primary_key=True)
    target_type = Column(String, nullable=False)  # 'group', 'channel', 'user'
    target_id = Column(String, nullable=False, index=True)
    target_username = Column(String, nullable=True)
    target_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # Higher priority = reported more often
    added_by = Column(Integer, nullable=False)  # User ID who added it
    report_count = Column(Integer, default=0, nullable=False)
    last_reported = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_targets_id', 'target_id'),
        Index('idx_targets_active', 'is_active'),
        Index('idx_targets_priority', 'priority'),
        Index('idx_targets_type', 'target_type'),
        UniqueConstraint('target_type', 'target_id', name='uq_target_type_id'),
    )
    
    def __repr__(self):
        return f"<ReportTarget({self.target_type}: {self.target_id})>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_username': self.target_username,
            'is_active': self.is_active,
            'priority': self.priority,
            'report_count': self.report_count
        }


class ReportStats(Base):
    """Statistics model for tracking daily reports"""
    __tablename__ = 'report_stats'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, default=datetime.utcnow().date, nullable=False, index=True)
    account_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    target_id = Column(String, nullable=True)
    reports_count = Column(Integer, default=0, nullable=False)
    successful_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_stats_date', 'date'),
        Index('idx_stats_account_date', 'account_id', 'date'),
    )


# ============================================
# DATABASE INITIALIZATION
# ============================================

def init_db():
    """Initialize database tables"""
    try:
        Base.metadata.create_all(engine)
        logger.info("✅ Database tables created successfully")
        
        # Log table names
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"📊 Tables: {', '.join(tables)}")
        
    except Exception as e:
        logger.error(f"❌ Error creating database tables: {e}")
        raise


def drop_db():
    """Drop all tables (use with caution!)"""
    try:
        Base.metadata.drop_all(engine)
        logger.warning("⚠️ All database tables dropped")
    except Exception as e:
        logger.error(f"❌ Error dropping database tables: {e}")


# ============================================
# DATABASE SESSION MANAGEMENT
# ============================================

@contextmanager
def get_db():
    """Context manager for database sessions"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


def get_db_session():
    """Get a new database session"""
    return SessionLocal()


# ============================================
# HELPER FUNCTIONS
# ============================================

def update_user_activity(session, user_id):
    """Update user's last activity timestamp"""
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if user:
            user.last_activity = datetime.utcnow()
            session.commit()
    except Exception as e:
        logger.error(f"Error updating user activity: {e}")
        session.rollback()


def get_active_accounts(session, user_id=None):
    """Get all active accounts, optionally filtered by user"""
    query = session.query(Account).filter_by(is_active=True)
    if user_id:
        query = query.filter_by(user_id=user_id)
    return query.all()


def get_active_targets(session):
    """Get all active targets sorted by priority"""
    return session.query(ReportTarget).filter_by(is_active=True).order_by(ReportTarget.priority.desc()).all()


def increment_report_count(session, account_id, target_id, success=True):
    """Increment report counts for account and target"""
    try:
        # Update account stats
        account = session.query(Account).filter_by(id=account_id).first()
        if account:
            account.reports_count += 1
            if success:
                account.successful_reports += 1
            else:
                account.failed_reports += 1
            account.last_report_time = datetime.utcnow()
        
        # Update target stats
        target = session.query(ReportTarget).filter_by(id=target_id).first()
        if target:
            target.report_count += 1
            target.last_reported = datetime.utcnow()
        
        session.commit()
    except Exception as e:
        logger.error(f"Error incrementing report count: {e}")
        session.rollback()


# Initialize database on import
init_db()

# Export commonly used functions and classes
__all__ = [
    'Base',
    'engine',
    'SessionLocal',
    'db_session',
    'get_db',
    'get_db_session',
    'init_db',
    'drop_db',
    'User',
    'Account',
    'Report',
    'ReportTarget',
    'ReportStats',
    'update_user_activity',
    'get_active_accounts',
    'get_active_targets',
    'increment_report_count'
]