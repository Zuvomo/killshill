"""
Database utility functions for handling Supabase SSL connection issues
"""

import time
import logging
from functools import wraps
from django.db import connection, transaction
from django.db.utils import OperationalError
import psycopg2

logger = logging.getLogger(__name__)

def retry_db_connection(max_retries=3, delay=1, backoff=2):
    """
    Decorator to retry database operations when SSL connection failures occur
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (OperationalError, psycopg2.OperationalError) as e:
                    error_msg = str(e).lower()
                    
                    # Check if it's an SSL connection issue
                    ssl_errors = [
                        'ssl connection has been closed unexpectedly',
                        'connection to server',
                        'ssl error',
                        'server closed the connection unexpectedly',
                        'connection timed out'
                    ]
                    
                    if any(ssl_error in error_msg for ssl_error in ssl_errors):
                        retries += 1
                        if retries < max_retries:
                            logger.warning(
                                f"SSL connection error in {func.__name__}, "
                                f"retry {retries}/{max_retries} in {delay}s: {e}"
                            )
                            
                            # Force close the connection to get a fresh one
                            connection.close()
                            time.sleep(delay)
                            delay *= backoff
                        else:
                            logger.error(
                                f"SSL connection failed after {max_retries} retries "
                                f"in {func.__name__}: {e}"
                            )
                            raise
                    else:
                        # Not an SSL error, re-raise immediately
                        raise
                except Exception as e:
                    # Other exceptions, re-raise immediately
                    logger.error(f"Non-SSL error in {func.__name__}: {e}")
                    raise
            
            return None
        return wrapper
    return decorator

def ensure_db_connection():
    """
    Ensure database connection is alive and reconnect if necessary
    """
    try:
        connection.ensure_connection()
        # Test the connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception as e:
        logger.warning(f"Database connection test failed: {e}")
        connection.close()
        return False

def safe_db_query(query_func):
    """
    Execute a database query with automatic retry for SSL issues
    """
    @retry_db_connection(max_retries=3, delay=1)
    def execute_query():
        ensure_db_connection()
        return query_func()
    
    return execute_query()

class DatabaseConnectionManager:
    """
    Context manager for database operations with SSL error handling
    """
    
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        self.retries = 0
    
    def __enter__(self):
        self.ensure_connection()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and issubclass(exc_type, (OperationalError, psycopg2.OperationalError)):
            error_msg = str(exc_val).lower()
            ssl_errors = [
                'ssl connection has been closed unexpectedly',
                'connection to server',
                'ssl error'
            ]
            
            if any(ssl_error in error_msg for ssl_error in ssl_errors):
                self.retries += 1
                if self.retries < self.max_retries:
                    logger.warning(f"SSL error in transaction, closing connection: {exc_val}")
                    connection.close()
                    return True  # Suppress the exception
        
        return False  # Let other exceptions propagate
    
    def ensure_connection(self):
        """Ensure we have a valid database connection"""
        if not ensure_db_connection():
            # Try to reconnect
            connection.connect()

# Utility function for views and services
def with_db_retry(func):
    """
    Simple decorator for view functions to handle DB SSL issues
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (OperationalError, psycopg2.OperationalError) as e:
            error_msg = str(e).lower()
            if 'ssl connection has been closed unexpectedly' in error_msg:
                logger.warning(f"SSL connection lost in {func.__name__}, retrying...")
                connection.close()
                # Retry once
                return func(*args, **kwargs)
            else:
                raise
    return wrapper