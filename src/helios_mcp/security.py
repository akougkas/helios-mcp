"""Security utilities for Helios MCP server.

Provides path validation, input sanitization, and secure operations
to prevent common vulnerabilities like path traversal and injection attacks.
"""

import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Union, Set
import logging
from pydantic import BaseModel, Field, validator, ValidationError

logger = logging.getLogger(__name__)


# Allowed characters for various input types
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
SAFE_PERSONA_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
SAFE_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')

# Dangerous path components
DANGEROUS_PATH_COMPONENTS = {
    '..',
    '.',
    '~',
    '//',
    '\\',
    '\0',
}

# Allowed configuration domains and keys
ALLOWED_DOMAINS = {
    'behaviors',
    'communication',
    'technical',
    'identity',
    'preferences',
    'specializations',
    'learning'
}

ALLOWED_PARAMETERS = {
    'base_importance',
    'specialization_level',
    'learning_rate',
    'version'
}


class SecurityError(Exception):
    """Base exception for security violations."""
    pass


class PathTraversalError(SecurityError):
    """Raised when path traversal attempts are detected."""
    pass


class InvalidInputError(SecurityError):
    """Raised when input validation fails."""
    pass


class BaseConfigSchema(BaseModel):
    """Pydantic schema for base configuration validation."""
    base_importance: float = Field(
        ge=0.0, le=1.0,
        description="Base configuration importance weight"
    )
    identity: Optional[Dict[str, Any]] = None
    communication: Optional[Dict[str, Any]] = None
    behaviors: Optional[Dict[str, Any]] = None
    technical: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    version: Optional[str] = Field(pattern=r'^\d+\.\d+\.\d+$')
    description: Optional[str] = Field(max_length=1000)
    created: Optional[str] = None
    
    class Config:
        extra = "allow"  # Allow additional fields but validate known ones


class PersonaConfigSchema(BaseModel):
    """Pydantic schema for persona configuration validation."""
    specialization_level: float = Field(
        ge=1.0,
        description="Specialization level (must be >= 1.0)"
    )
    name: Optional[str] = Field(max_length=100, pattern=r'^[a-zA-Z0-9 _-]+$')
    description: Optional[str] = Field(max_length=1000)
    behaviors: Optional[Dict[str, Any]] = None
    specializations: Optional[Dict[str, Any]] = None
    learning_rate: Optional[float] = Field(ge=0.0, le=1.0)
    version: Optional[str] = Field(pattern=r'^\d+\.\d+\.\d+$')
    
    class Config:
        extra = "allow"  # Allow additional fields but validate known ones


def validate_persona_name(name: str) -> str:
    """Validate and sanitize persona name.
    
    Args:
        name: Persona name to validate
        
    Returns:
        Validated persona name
        
    Raises:
        InvalidInputError: If name is invalid or contains dangerous characters
    """
    if not name or not isinstance(name, str):
        raise InvalidInputError("Persona name must be a non-empty string")
    
    # Remove any whitespace
    name = name.strip()
    
    if not name:
        raise InvalidInputError("Persona name cannot be empty")
        
    if len(name) > 50:
        raise InvalidInputError("Persona name too long (max 50 characters)")
    
    # Check for dangerous characters
    if not SAFE_PERSONA_NAME_PATTERN.match(name):
        raise InvalidInputError(
            f"Persona name contains invalid characters. "
            f"Only alphanumeric, underscore, and hyphen allowed: {name}"
        )
    
    # Additional security checks
    if name.startswith('.'):
        raise InvalidInputError("Persona name cannot start with a dot")
        
    if any(dangerous in name for dangerous in DANGEROUS_PATH_COMPONENTS):
        raise InvalidInputError(f"Persona name contains dangerous components: {name}")
    
    return name


def validate_file_path(file_path: Union[str, Path], base_dir: Path) -> Path:
    """Validate file path to prevent path traversal attacks.
    
    Args:
        file_path: Path to validate
        base_dir: Base directory that the path must be within
        
    Returns:
        Validated and resolved Path object
        
    Raises:
        PathTraversalError: If path traversal is attempted
        InvalidInputError: If path is invalid
    """
    if not file_path:
        raise InvalidInputError("File path cannot be empty")
    
    try:
        # Convert to Path object
        path_obj = Path(file_path).resolve()
        base_obj = base_dir.resolve()
        
        # Check if path is within base directory
        try:
            path_obj.relative_to(base_obj)
        except ValueError:
            raise PathTraversalError(
                f"Path traversal detected: {file_path} is outside {base_dir}"
            )
        
        # Additional checks for dangerous components
        path_parts = path_obj.parts
        if any(part in DANGEROUS_PATH_COMPONENTS for part in path_parts):
            raise PathTraversalError(
                f"Dangerous path components detected in: {file_path}"
            )
        
        # Check for null bytes
        if '\0' in str(file_path):
            raise InvalidInputError("Null byte detected in path")
            
        return path_obj
        
    except (OSError, ValueError) as e:
        raise InvalidInputError(f"Invalid file path: {file_path} - {e}")


def validate_config_key(key: str) -> str:
    """Validate configuration key for dot notation.
    
    Args:
        key: Configuration key to validate
        
    Returns:
        Validated key
        
    Raises:
        InvalidInputError: If key is invalid
    """
    if not key or not isinstance(key, str):
        raise InvalidInputError("Configuration key must be a non-empty string")
    
    key = key.strip()
    if not key:
        raise InvalidInputError("Configuration key cannot be empty")
        
    if len(key) > 200:
        raise InvalidInputError("Configuration key too long (max 200 characters)")
    
    # Check each part of dot-notation key
    key_parts = key.split('.')
    for part in key_parts:
        if not part:
            raise InvalidInputError(f"Empty key component in: {key}")
            
        if not SAFE_KEY_PATTERN.match(part):
            raise InvalidInputError(
                f"Invalid characters in key component '{part}'. "
                f"Only alphanumeric, underscore, hyphen, and dot allowed"
            )
    
    return key


def validate_config_domain(domain: str) -> str:
    """Validate configuration domain.
    
    Args:
        domain: Configuration domain to validate
        
    Returns:
        Validated domain
        
    Raises:
        InvalidInputError: If domain is not in allowed list
    """
    if not domain or not isinstance(domain, str):
        raise InvalidInputError("Configuration domain must be a non-empty string")
    
    domain = domain.strip()
    if domain not in ALLOWED_DOMAINS:
        raise InvalidInputError(
            f"Configuration domain '{domain}' not allowed. "
            f"Allowed domains: {', '.join(sorted(ALLOWED_DOMAINS))}"
        )
    
    return domain


def validate_parameter_name(parameter: str) -> str:
    """Validate parameter name for tuning operations.
    
    Args:
        parameter: Parameter name to validate
        
    Returns:
        Validated parameter name
        
    Raises:
        InvalidInputError: If parameter is not in allowed list
    """
    if not parameter or not isinstance(parameter, str):
        raise InvalidInputError("Parameter name must be a non-empty string")
    
    parameter = parameter.strip()
    if parameter not in ALLOWED_PARAMETERS:
        raise InvalidInputError(
            f"Parameter '{parameter}' not allowed. "
            f"Allowed parameters: {', '.join(sorted(ALLOWED_PARAMETERS))}"
        )
    
    return parameter


def sanitize_git_message(message: str) -> str:
    """Sanitize git commit message to prevent injection.
    
    Args:
        message: Commit message to sanitize
        
    Returns:
        Sanitized commit message
        
    Raises:
        InvalidInputError: If message is invalid
    """
    if not message or not isinstance(message, str):
        raise InvalidInputError("Commit message must be a non-empty string")
    
    message = message.strip()
    if not message:
        raise InvalidInputError("Commit message cannot be empty")
        
    if len(message) > 500:
        raise InvalidInputError("Commit message too long (max 500 characters)")
    
    # Remove dangerous characters that could be used for injection
    dangerous_chars = ['\0', '\n', '\r', ';', '&', '|', '`', '$', '(', ')']
    for char in dangerous_chars:
        if char in message:
            message = message.replace(char, ' ')
    
    # Remove multiple spaces
    message = re.sub(r'\s+', ' ', message).strip()
    
    return message


def validate_commits_back(commits_back: int) -> int:
    """Validate number of commits to revert.
    
    Args:
        commits_back: Number of commits to revert
        
    Returns:
        Validated commits_back value
        
    Raises:
        InvalidInputError: If value is out of safe range
    """
    if not isinstance(commits_back, int):
        raise InvalidInputError("commits_back must be an integer")
    
    if commits_back < 1 or commits_back > 10:
        raise InvalidInputError("commits_back must be between 1 and 10")
    
    return commits_back


def validate_base_config(data: Dict[str, Any]) -> BaseConfigSchema:
    """Validate base configuration using Pydantic schema.
    
    Args:
        data: Configuration data to validate
        
    Returns:
        Validated configuration schema
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        return BaseConfigSchema(**data)
    except ValidationError as e:
        logger.error(f"Base configuration validation failed: {e}")
        raise InvalidInputError(f"Invalid base configuration: {e}")


def validate_persona_config(data: Dict[str, Any]) -> PersonaConfigSchema:
    """Validate persona configuration using Pydantic schema.
    
    Args:
        data: Configuration data to validate
        
    Returns:
        Validated configuration schema
        
    Raises:
        ValidationError: If validation fails
    """
    try:
        return PersonaConfigSchema(**data)
    except ValidationError as e:
        logger.error(f"Persona configuration validation failed: {e}")
        raise InvalidInputError(f"Invalid persona configuration: {e}")


def create_safe_git_command(base_command: List[str], *args: str) -> List[str]:
    """Create a safe git command with properly quoted arguments.
    
    Args:
        base_command: Base command parts (e.g., ['git', '-C', '/path'])
        *args: Additional arguments to add safely
        
    Returns:
        List of command parts with safely quoted arguments
    """
    safe_command = base_command.copy()
    
    for arg in args:
        if not isinstance(arg, str):
            raise InvalidInputError(f"Git command argument must be string, got {type(arg)}")
        
        # Use shlex.quote for proper shell escaping
        safe_arg = shlex.quote(arg)
        safe_command.append(safe_arg)
    
    return safe_command


def sanitize_error_message(error: Exception) -> str:
    """Sanitize error message for safe display to users.
    
    Args:
        error: Exception to sanitize
        
    Returns:
        Sanitized error message
    """
    error_str = str(error)
    
    # Remove potentially sensitive information
    # Replace full paths with just filenames
    error_str = re.sub(r'/[^\s]*/', '.../', error_str)
    
    # Limit length
    if len(error_str) > 200:
        error_str = error_str[:197] + '...'
    
    return error_str
