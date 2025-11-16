# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

"""Repository for configuration CRUD operations."""

from typing import List, Optional, Any, Dict
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.adapters.database.postgres.models import ConfigTable


class ConfigRepository:
    """Repository for managing configuration database operations."""
    
    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def create(
        self,
        config_key: str,
        config_value: str,
        value_type: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_secret: bool = False,
        is_system: bool = False,
        updated_by: Optional[str] = None,
    ) -> ConfigTable:
        """
        Create a new configuration entry in the database.
        
        Args:
            config_key: Unique key for the configuration
            config_value: Configuration value (stored as string)
            value_type: Type of value (string, int, float, bool, json)
            description: Description of the configuration (optional)
            category: Category for grouping (optional)
            is_secret: Whether this is a secret value (optional)
            is_system: Whether this is a system config (optional)
            updated_by: Who created this config (optional)
            
        Returns:
            Created ConfigTable object
        """
        config = ConfigTable(
            config_key=config_key,
            config_value=config_value,
            value_type=value_type,
            description=description,
            category=category,
            is_secret=is_secret,
            is_system=is_system,
            updated_by=updated_by,
        )
        
        self.session.add(config)
        self.session.commit()
        self.session.refresh(config)
        
        return config
    
    def get_by_key(self, config_key: str) -> Optional[ConfigTable]:
        """
        Retrieve a configuration by its key.
        
        Args:
            config_key: The unique key of the configuration
            
        Returns:
            ConfigTable object if found, None otherwise
        """
        stmt = select(ConfigTable).where(ConfigTable.config_key == config_key)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_value(self, config_key: str, default: Any = None) -> Any:
        """
        Get the parsed value of a configuration.
        
        Args:
            config_key: The unique key of the configuration
            default: Default value if not found
            
        Returns:
            Parsed configuration value or default
        """
        config = self.get_by_key(config_key)
        if not config:
            return default
        
        return self._parse_value(config.config_value, config.value_type)
    
    def list_configs(
        self,
        category: Optional[str] = None,
        is_secret: Optional[bool] = None,
        is_system: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ConfigTable]:
        """
        List configurations with optional filtering.
        
        Args:
            category: Filter by category
            is_secret: Filter by is_secret flag
            is_system: Filter by is_system flag
            limit: Maximum number of results to return (default: 100)
            offset: Number of results to skip (default: 0)
            
        Returns:
            List of ConfigTable objects
        """
        stmt = select(ConfigTable)
        
        # Apply filters
        conditions = []
        if category:
            conditions.append(ConfigTable.category == category)
        if is_secret is not None:
            conditions.append(ConfigTable.is_secret == is_secret)
        if is_system is not None:
            conditions.append(ConfigTable.is_system == is_system)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        # Order by config_key
        stmt = stmt.order_by(ConfigTable.config_key.asc())
        
        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)
        
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def update(
        self,
        config_key: str,
        config_value: Optional[str] = None,
        value_type: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_secret: Optional[bool] = None,
        updated_by: Optional[str] = None,
    ) -> Optional[ConfigTable]:
        """
        Update an existing configuration.
        
        Args:
            config_key: The unique key of the configuration to update
            config_value: New configuration value
            value_type: New value type
            description: New description
            category: New category
            is_secret: New is_secret flag
            updated_by: Who updated this config
            
        Returns:
            Updated ConfigTable object if found, None otherwise
        """
        config = self.get_by_key(config_key)
        if not config:
            return None
        
        # Update fields if provided
        if config_value is not None:
            config.config_value = config_value
        if value_type is not None:
            config.value_type = value_type
        if description is not None:
            config.description = description
        if category is not None:
            config.category = category
        if is_secret is not None:
            config.is_secret = is_secret
        if updated_by is not None:
            config.updated_by = updated_by
        
        # Update the updated_at timestamp
        config.updated_at = datetime.utcnow()
        
        self.session.commit()
        self.session.refresh(config)
        
        return config
    
    def upsert(
        self,
        config_key: str,
        config_value: str,
        value_type: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_secret: bool = False,
        is_system: bool = False,
        updated_by: Optional[str] = None,
    ) -> ConfigTable:
        """
        Create or update a configuration (upsert).
        
        Args:
            config_key: Unique key for the configuration
            config_value: Configuration value
            value_type: Type of value
            description: Description of the configuration
            category: Category for grouping
            is_secret: Whether this is a secret value
            is_system: Whether this is a system config
            updated_by: Who created/updated this config
            
        Returns:
            ConfigTable object (created or updated)
        """
        existing = self.get_by_key(config_key)
        
        if existing:
            return self.update(
                config_key=config_key,
                config_value=config_value,
                value_type=value_type,
                description=description,
                category=category,
                is_secret=is_secret,
                updated_by=updated_by,
            )
        else:
            return self.create(
                config_key=config_key,
                config_value=config_value,
                value_type=value_type,
                description=description,
                category=category,
                is_secret=is_secret,
                is_system=is_system,
                updated_by=updated_by,
            )
    
    def delete(self, config_key: str) -> bool:
        """
        Delete a configuration by key.
        
        Args:
            config_key: The unique key of the configuration to delete
            
        Returns:
            True if deleted, False if not found
        """
        config = self.get_by_key(config_key)
        if not config:
            return False
        
        # Prevent deletion of system configs
        if config.is_system:
            return False
        
        self.session.delete(config)
        self.session.commit()
        
        return True
    
    def get_by_category(self, category: str) -> List[ConfigTable]:
        """
        Get all configurations in a category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of ConfigTable objects in the category
        """
        stmt = (
            select(ConfigTable)
            .where(ConfigTable.category == category)
            .order_by(ConfigTable.config_key.asc())
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_all_categories(self) -> List[str]:
        """
        Get all unique categories.
        
        Returns:
            List of unique category names
        """
        stmt = select(ConfigTable.category).distinct().where(ConfigTable.category != None)
        result = self.session.execute(stmt)
        return [row[0] for row in result.all()]
    
    def get_user_editable_configs(self) -> List[ConfigTable]:
        """
        Get all user-editable (non-system) configurations.
        
        Returns:
            List of user-editable ConfigTable objects
        """
        stmt = (
            select(ConfigTable)
            .where(ConfigTable.is_system == False)
            .order_by(ConfigTable.config_key.asc())
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    def get_configs_as_dict(
        self,
        category: Optional[str] = None,
        include_secrets: bool = False,
    ) -> Dict[str, Any]:
        """
        Get configurations as a dictionary with parsed values.
        
        Args:
            category: Filter by category (optional)
            include_secrets: Whether to include secret values (default: False)
            
        Returns:
            Dictionary mapping config keys to parsed values
        """
        if category:
            configs = self.get_by_category(category)
        else:
            configs = self.list_configs(limit=1000)
        
        result = {}
        for config in configs:
            # Skip secrets if not requested
            if config.is_secret and not include_secrets:
                continue
            
            result[config.config_key] = self._parse_value(
                config.config_value,
                config.value_type
            )
        
        return result
    
    def _parse_value(self, value: str, value_type: str) -> Any:
        """
        Parse a configuration value based on its type.
        
        Args:
            value: String value to parse
            value_type: Type of the value
            
        Returns:
            Parsed value
        """
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "json":
            import json
            return json.loads(value)
        else:  # string
            return value
