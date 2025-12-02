"""
Data Migration Script
Migrates existing data to the new user-based model
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from devsend.config import settings
from devsend.models import (
    Base, User, Recipient, EmailTemplate, ApiKey, 
    EmailLog, ScheduledJob, SenderProfile
)
from devsend.auth import get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_data():
    """Migrate existing data to include user_id references"""
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        inspector = inspect(engine)
        
        # Check if User table exists and has data
        if 'users' not in inspector.get_table_names():
            logger.info("Creating new database schema...")
            Base.metadata.create_all(bind=engine)
        
        # Create or get default admin user
        admin_user = db.query(User).filter(User.username == settings.admin_username).first()
        
        if not admin_user:
            logger.info(f"Creating default admin user: {settings.admin_username}")
            admin_user = User(
                username=settings.admin_username,
                hashed_password=get_password_hash(settings.admin_password),
                is_admin=True,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            logger.info(f"Admin user created with ID: {admin_user.id}")
        else:
            logger.info(f"Using existing admin user with ID: {admin_user.id}")
        
        # Check if old data exists without user_id
        tables_to_migrate = [
            ('recipients', Recipient),
            ('email_templates', EmailTemplate),
            ('api_keys', ApiKey),
            ('email_logs', EmailLog),
            ('scheduled_jobs', ScheduledJob),
            ('sender_profiles', SenderProfile)
        ]
        
        for table_name, model_class in tables_to_migrate:
            if table_name not in inspector.get_table_names():
                continue
                
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            
            if 'user_id' not in columns:
                logger.info(f"Adding user_id column to {table_name}...")
                # SQLite doesn't support ALTER TABLE ADD COLUMN with NOT NULL, so we do it in steps
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER"))
                    conn.execute(text(f"UPDATE {table_name} SET user_id = {admin_user.id} WHERE user_id IS NULL"))
                    conn.commit()
                logger.info(f"Migrated {table_name} data to admin user")
            else:
                # Update any existing NULL user_id values
                count = db.query(model_class).filter(
                    getattr(model_class, 'user_id') == None
                ).update({model_class.user_id: admin_user.id})
                
                if count > 0:
                    db.commit()
                    logger.info(f"Updated {count} records in {table_name} with admin user_id")
        
        logger.info("✓ Migration completed successfully!")
        logger.info(f"All existing data has been assigned to user: {admin_user.username}")
        
        # Print summary
        logger.info("\nData Summary:")
        logger.info(f"  Recipients: {db.query(Recipient).filter(Recipient.user_id == admin_user.id).count()}")
        logger.info(f"  Templates: {db.query(EmailTemplate).filter(EmailTemplate.user_id == admin_user.id).count()}")
        logger.info(f"  API Keys: {db.query(ApiKey).filter(ApiKey.user_id == admin_user.id).count()}")
        logger.info(f"  Email Logs: {db.query(EmailLog).filter(EmailLog.user_id == admin_user.id).count()}")
        logger.info(f"  Scheduled Jobs: {db.query(ScheduledJob).filter(ScheduledJob.user_id == admin_user.id).count()}")
        logger.info(f"  Sender Profiles: {db.query(SenderProfile).filter(SenderProfile.user_id == admin_user.id).count()}")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_data()
