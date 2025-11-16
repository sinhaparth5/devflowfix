# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Database connection pool management with Lambda support."""

import os
import logging
from typing import Generator, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration with environment-aware settings."""
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        is_lambda: Optional[bool] = None,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        echo: bool = False,
        echo_pool: bool = False,
    ):
        """
        Initialize database configuration.
        
        Args:
            database_url: PostgreSQL connection URL (falls back to env var)
            is_lambda: Whether running in AWS Lambda (auto-detected if None)
            pool_size: Number of connections to maintain in pool (ignored in Lambda)
            max_overflow: Max connections beyond pool_size (ignored in Lambda)
            pool_timeout: Seconds to wait for connection from pool
            pool_recycle: Seconds before recycling connections
            pool_pre_ping: Test connections before using
            echo: Log all SQL statements
            echo_pool: Log connection pool events
        """
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/devflowfix"
        )
        
        if is_lambda is None:
            self.is_lambda = self._is_running_in_lambda()
        else:
            self.is_lambda = is_lambda
        
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.pool_pre_ping = pool_pre_ping
        self.echo = echo
        self.echo_pool = echo_pool
    
    @staticmethod
    def _is_running_in_lambda() -> bool:
        """
        Detect if running in AWS Lambda environment.
        
        Returns:
            True if running in Lambda, False otherwise
        """
        return (
            os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None
            or os.getenv("AWS_EXECUTION_ENV") is not None
        )
    
    def get_engine_kwargs(self) -> dict:
        """
        Get SQLAlchemy engine configuration based on environment.
        
        Returns:
            Dictionary of engine configuration parameters
        """
        kwargs = {
            "echo": self.echo,
            "echo_pool": self.echo_pool,
            "pool_pre_ping": self.pool_pre_ping,
        }
        
        if self.is_lambda:
            logger.info("Configuring database for AWS Lambda (NullPool)")
            kwargs["poolclass"] = NullPool
        else:
            logger.info("Configuring database with connection pool (QueuePool)")
            kwargs["poolclass"] = QueuePool
            kwargs["pool_size"] = self.pool_size
            kwargs["max_overflow"] = self.max_overflow
            kwargs["pool_timeout"] = self.pool_timeout
            kwargs["pool_recycle"] = self.pool_recycle
        
        return kwargs


class DatabaseConnectionPool:
    """
    Database connection pool manager.
    
    Manages SQLAlchemy engine and session lifecycle with support for
    both traditional deployments and AWS Lambda environments.
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize the connection pool.
        
        Args:
            config: Database configuration (creates default if None)
        """
        self.config = config or DatabaseConfig()
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._initialized = False
    
    @property
    def engine(self) -> Engine:
        """
        Get the SQLAlchemy engine, creating it if necessary.
        
        Returns:
            SQLAlchemy engine instance
        """
        if not self._initialized:
            self.initialize()
        return self._engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """
        Get the session factory, creating it if necessary.
        
        Returns:
            SQLAlchemy sessionmaker instance
        """
        if not self._initialized:
            self.initialize()
        return self._session_factory
    
    def initialize(self) -> None:
        """
        Initialize the database engine and session factory.
        
        This method is idempotent and safe to call multiple times.
        """
        if self._initialized:
            logger.debug("Database connection pool already initialized")
            return
        
        logger.info(f"Initializing database connection pool (Lambda: {self.config.is_lambda})")
        
        try:
            engine_kwargs = self.config.get_engine_kwargs()
            self._engine = create_engine(
                self.config.database_url,
                **engine_kwargs
            )
            
            self._register_event_listeners(self._engine)
            
            self._session_factory = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self._engine
            )
            
            self._initialized = True
            logger.info("Database connection pool initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise
    
    def _register_event_listeners(self, engine: Engine) -> None:
        """
        Register SQLAlchemy event listeners for monitoring and debugging.
        
        Args:
            engine: SQLAlchemy engine instance
        """
        @event.listens_for(engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """Handle new connection creation."""
            logger.debug("New database connection established")
        
        @event.listens_for(engine, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            """Handle connection checkout from pool."""
            logger.debug("Connection checked out from pool")
        
        @event.listens_for(engine, "checkin")
        def receive_checkin(dbapi_conn, connection_record):
            """Handle connection checkin to pool."""
            logger.debug("Connection checked in to pool")
    
    def get_session(self) -> Session:
        """
        Create a new database session.
        
        Returns:
            SQLAlchemy session instance
            
        Note:
            Caller is responsible for closing the session.
        """
        return self.session_factory()
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Provide a transactional scope for a series of operations.
        
        Yields:
            SQLAlchemy session instance
            
        Example:
            ```python
            with pool.session_scope() as session:
                incident = session.query(Incident).first()
                # ... do work ...
                # session commits automatically on success
                # session rolls back on exception
            ```
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session rolled back due to error: {e}")
            raise
        finally:
            session.close()
    
    def dispose(self) -> None:
        """
        Dispose of the connection pool.
        
        This should be called when shutting down the application or
        when you want to recreate the connection pool with new settings.
        """
        if self._engine:
            logger.info("Disposing database connection pool")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
    
    def test_connection(self) -> bool:
        """
        Test the database connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            with self.session_scope() as session:
                from sqlalchemy import text
                result = session.execute(text("SELECT 1")).scalar()
                return result == 1
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def get_pool_status(self) -> dict:
        """
        Get current connection pool status.
        
        Returns:
            Dictionary with pool statistics
        """
        if not self._initialized or self.config.is_lambda:
            return {
                "pool_type": "NullPool" if self.config.is_lambda else "Not initialized",
                "active_connections": "N/A",
            }
        
        pool_obj = self._engine.pool
        return {
            "pool_type": pool_obj.__class__.__name__,
            "pool_size": pool_obj.size(),
            "checked_out": pool_obj.checkedout(),
            "overflow": pool_obj.overflow(),
            "queue_size": pool_obj.size() - pool_obj.checkedout(),
        }


_connection_pool: Optional[DatabaseConnectionPool] = None


def get_connection_pool(config: Optional[DatabaseConfig] = None) -> DatabaseConnectionPool:
    """
    Get or create the global database connection pool.
    
    Args:
        config: Database configuration (only used on first call)
        
    Returns:
        DatabaseConnectionPool instance
    """
    global _connection_pool
    
    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool(config)
        _connection_pool.initialize()
    
    return _connection_pool


def get_db_session() -> Generator[Session, None, None]:
    """
    Dependency function for FastAPI to get database sessions.
    
    Yields:
        SQLAlchemy session instance
        
    Example:
        ```python
        @app.get("/incidents")
        def list_incidents(db: Session = Depends(get_db_session)):
            return db.query(Incident).all()
        ```
    """
    pool = get_connection_pool()
    session = pool.get_session()
    try:
        yield session
    finally:
        session.close()


def reset_connection_pool() -> None:
    """
    Reset the global connection pool.
    
    Useful for testing or when database configuration changes.
    """
    global _connection_pool
    
    if _connection_pool:
        _connection_pool.dispose()
        _connection_pool = None


def get_lambda_session() -> Session:
    """
    Get a database session configured for Lambda environment.
    
    Returns:
        SQLAlchemy session instance
        
    Note:
        This creates a new connection for each invocation (NullPool).
        Caller must close the session after use.
        
    Example:
        ```python
        def lambda_handler(event, context):
            session = get_lambda_session()
            try:
                # ... do work ...
                session.commit()
            except Exception as e:
                session.rollback()
                raise
            finally:
                session.close()
        ```
    """
    config = DatabaseConfig(is_lambda=True)
    pool = DatabaseConnectionPool(config)
    pool.initialize()
    return pool.get_session()
