"""Helios MCP Server - Configuration management for AI behaviors."""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import asdict
import subprocess
import datetime
import re

from fastmcp import FastMCP, Context
from pydantic import Field

from .config import HeliosConfig, ConfigLoader
from .inheritance import create_behavior_merger, InheritanceCalculator
from .git_store import GitStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("Helios")

# Global configuration
config = HeliosConfig.default()
loader = ConfigLoader(config)
git_store = GitStore(config.base_path.parent)  # ~/.helios directory


@mcp.tool(
    description="Load the base configuration that defines core AI behaviors and inheritance patterns",
    tags={"config", "base"}
)
async def get_base_config(
    ctx: Context = None
) -> Dict[str, Any]:
    """Load base configuration with core behaviors and inheritance settings.
    
    Returns:
        Dictionary containing base behaviors, preferences, and inheritance weight
    """
    try:
        if ctx:
            await ctx.info("Loading base configuration...")
        
        # Try to load identity.yaml first, then fall back to config.yaml
        identity_file = config.base_path / "identity.yaml"
        if identity_file.exists():
            base_config = await loader.load_yaml(identity_file)
            config_path = str(identity_file)
        else:
            base_config = await loader.load_base_config()
            config_path = str(config.base_path / "config.yaml")
        
        if ctx:
            await ctx.info(f"Loaded base config with {len(base_config)} sections")
        
        return {
            "status": "success",
            "config": base_config,
            "path": config_path
        }
    except Exception as e:
        logger.error(f"Failed to load base config: {e}")
        return {
            "status": "error",
            "message": str(e),
            "fallback_config": {
                "behaviors": {"communication_style": "helpful"},
                "base_importance": 0.5
            }
        }


@mcp.tool(
    description="Retrieve a specific persona configuration with specialized behaviors",
    tags={"config", "persona"}
)
async def get_active_persona(
    persona_name: str = Field(description="Name of the persona to retrieve"),
    ctx: Context = None
) -> Dict[str, Any]:
    """Load specific persona configuration.
    
    Args:
        persona_name: Name of the persona configuration to load
        
    Returns:
        Dictionary containing persona behaviors and specialization level
    """
    try:
        if ctx:
            await ctx.info(f"Loading persona '{persona_name}'...")
        
        persona_config = await loader.load_persona_config(persona_name)
        
        if persona_config is None:
            # Return sample persona for testing
            sample_persona = {
                "behaviors": {
                    "communication_style": "technical",
                    "response_length": "detailed",
                    "domain_focus": "software_development"
                },
                "specialization_level": 2,
                "learning_rate": 0.1,
                "version": "1.0"
            }
            
            if ctx:
                await ctx.info(f"Persona '{persona_name}' not found, returning sample")
            
            return {
                "status": "not_found",
                "persona": sample_persona,
                "message": f"Persona '{persona_name}' not found, showing sample structure"
            }
        
        if ctx:
            await ctx.info(f"Successfully loaded persona '{persona_name}'")
        
        return {
            "status": "success",
            "persona": persona_config,
            "path": str(config.personas_path / f"{persona_name}.yaml")
        }
        
    except Exception as e:
        logger.error(f"Failed to load persona '{persona_name}': {e}")
        return {
            "status": "error",
            "message": str(e),
            "persona_name": persona_name
        }


@mcp.tool(
    description="Merge base and persona behaviors using weighted inheritance calculation",
    tags={"inheritance", "behaviors"}
)
async def merge_behaviors(
    persona_name: str = Field(description="Name of the persona to merge with base"),
    ctx: Context = None
) -> Dict[str, Any]:
    """Calculate merged behaviors using inheritance weights.
    
    This is the core of Helios - weighted inheritance calculation:
    inheritance_weight = base_importance / (specialization_level ** 2)
    merged_behavior = base * inheritance_weight + persona * (1 - inheritance_weight)
    
    Args:
        persona_name: Name of the persona to merge with base configuration
        
    Returns:
        Dictionary containing merged behaviors and inheritance calculations
    """
    try:
        if ctx:
            await ctx.info(f"Calculating inheritance for persona '{persona_name}'...")
        
        # Load base and persona configs
        base_result = await get_base_config(ctx)
        persona_result = await get_active_persona(persona_name, ctx)
        
        if base_result["status"] != "success":
            return {"status": "error", "message": "Failed to load base config"}
        
        base_config = base_result["config"]
        
        # Handle persona not found case
        if persona_result["status"] == "not_found":
            persona_config = persona_result["persona"]
        elif persona_result["status"] != "success":
            return {"status": "error", "message": "Failed to load persona config"}
        else:
            persona_config = persona_result["persona"]
        
        # Calculate inheritance weight using the real InheritanceCalculator
        base_importance = base_config.get("base_importance", 0.7)
        specialization_level = persona_config.get("specialization_level", 1)
        
        # Create behavior merger with the inheritance parameters
        merger = create_behavior_merger(base_importance, specialization_level)
        
        if ctx:
            await ctx.info(f"Calculated inheritance weight: {merger.inheritance_weight:.3f}")
        
        # Merge behaviors using the real BehaviorMerger
        merged_behaviors = merger.merge_behaviors(base_config, persona_config)
        
        return {
            "status": "success",
            "merged_behaviors": merged_behaviors,
            "calculation": {
                "base_importance": base_importance,
                "specialization_level": specialization_level,
                "inheritance_weight": inheritance_weight,
                "persona_weight": 1 - inheritance_weight
            },
            "persona_name": persona_name
        }
        
    except Exception as e:
        logger.error(f"Failed to merge behaviors for '{persona_name}': {e}")
        return {
            "status": "error",
            "message": str(e),
            "persona_name": persona_name
        }


@mcp.tool(
    description="Commit configuration changes to git for versioned behavior tracking",
    tags={"git", "persistence"}
)
async def commit_changes(
    message: str = Field(description="Commit message describing the changes"),
    files: Optional[list[str]] = Field(default=None, description="Specific files to commit (optional)"),
    ctx: Context = None
) -> Dict[str, Any]:
    """Commit configuration changes using git for behavior versioning.
    
    Args:
        message: Descriptive commit message
        files: Optional list of specific files to commit
        
    Returns:
        Dictionary with commit status and git information
    """
    try:
        if ctx:
            await ctx.info(f"Committing changes: {message}")
        
        # Use the real GitStore for git operations
        success = git_store.auto_commit(message)
        
        if success:
            # Get the latest commit info
            repo_status = git_store.get_repo_status()
            
            commit_info = {
                "commit_hash": repo_status.get("current_commit", "unknown")[:8],
                "timestamp": datetime.datetime.now().isoformat(),
                "message": message,
                "files_committed": files or ["all changes"],
                "author": "helios-mcp"
            }
        else:
            # No changes to commit
            commit_info = {
                "commit_hash": "no-changes",
                "timestamp": datetime.datetime.now().isoformat(),
                "message": message,
                "files_committed": [],
                "author": "helios-mcp",
                "note": "No changes to commit"
            }
        
        if ctx:
            await ctx.info(f"Successfully committed changes with hash: {commit_info['commit_hash']}")
        
        return {
            "status": "success",
            "commit": commit_info,
            "repository_path": str(config.base_path.parent)
        }
        
    except Exception as e:
        logger.error(f"Failed to commit changes: {e}")
        return {
            "status": "error",
            "message": str(e),
            "commit_message": message
        }


@mcp.tool(
    description="List all available personas in the configuration system",
    tags={"config", "list"}
)
async def list_personas(
    ctx: Context = None
) -> Dict[str, Any]:
    """List all available persona configurations.
    
    Returns:
        Dictionary containing list of available personas
    """
    try:
        if ctx:
            await ctx.info("Listing available personas...")
        
        personas = await loader.list_personas()
        
        if ctx:
            await ctx.info(f"Found {len(personas)} personas")
        
        return {
            "status": "success",
            "personas": personas,
            "count": len(personas),
            "personas_path": str(config.personas_path)
        }
        
    except Exception as e:
        logger.error(f"Failed to list personas: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@mcp.tool(
    description="Update and persist user preferences in base configuration",
    tags={"preferences", "persistence"}
)
async def update_preference(
    domain: str = Field(description="Preference domain (e.g., 'technical', 'communication')"),
    key: str = Field(description="Preference key to update"),
    value: str = Field(description="New preference value"),
    ctx: Context = None
) -> Dict[str, Any]:
    """Update and persist user preferences in base configuration.
    
    Args:
        domain: The configuration section to update
        key: The specific preference key
        value: The new value to set
        
    Returns:
        Dictionary with update status and new configuration
    """
    try:
        if ctx:
            await ctx.info(f"Updating preference {domain}.{key} = {value}")
        
        # Load current base config
        identity_file = config.base_path / "identity.yaml"
        if identity_file.exists():
            base_config = await loader.load_yaml(identity_file)
            config_file = identity_file
        else:
            base_config = await loader.load_base_config()
            config_file = config.base_path / "config.yaml"
        
        # Update the preference
        if domain not in base_config:
            base_config[domain] = {}
        
        # Handle nested keys (e.g., "communication.tone")
        if "." in key:
            keys = key.split(".")
            current = base_config[domain]
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value
        else:
            base_config[domain][key] = value
        
        # Save updated configuration
        await loader.save_yaml(config_file, base_config)
        
        if ctx:
            await ctx.info(f"Successfully updated and saved preference")
        
        return {
            "status": "success",
            "updated": {
                "domain": domain,
                "key": key,
                "value": value
            },
            "config_path": str(config_file)
        }
        
    except Exception as e:
        logger.error(f"Failed to update preference {domain}.{key}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "preference": f"{domain}.{key}"
        }


@mcp.tool(
    description="Search for learned behavioral patterns in the learned directory",
    tags={"patterns", "learning"}
)
async def search_patterns(
    query: str = Field(description="Search query for patterns"),
    confidence_min: float = Field(default=0.7, description="Minimum confidence threshold"),
    ctx: Context = None
) -> Dict[str, Any]:
    """Search for learned behavioral patterns.
    
    Args:
        query: Search query to match against patterns
        confidence_min: Minimum confidence threshold for results
        
    Returns:
        Dictionary containing matching patterns
    """
    try:
        if ctx:
            await ctx.info(f"Searching patterns for query: '{query}'")
        
        patterns = []
        learned_files = list(config.learned_path.glob("*.yaml"))
        
        for file in learned_files:
            try:
                pattern_data = await loader.load_yaml(file)
                
                # Simple text search in pattern data
                pattern_text = str(pattern_data).lower()
                query_lower = query.lower()
                
                # Check if query matches
                if query_lower in pattern_text:
                    confidence = pattern_data.get("confidence", 0.5)
                    
                    if confidence >= confidence_min:
                        patterns.append({
                            "file": file.stem,
                            "pattern": pattern_data,
                            "confidence": confidence,
                            "relevance_score": pattern_text.count(query_lower) / len(pattern_text)
                        })
            
            except Exception as e:
                logger.warning(f"Failed to load pattern file {file}: {e}")
                continue
        
        # Sort by confidence and relevance
        patterns.sort(key=lambda x: (x["confidence"], x["relevance_score"]), reverse=True)
        
        if ctx:
            await ctx.info(f"Found {len(patterns)} matching patterns")
        
        return {
            "status": "success",
            "patterns": patterns,
            "query": query,
            "confidence_threshold": confidence_min,
            "total_found": len(patterns)
        }
        
    except Exception as e:
        logger.error(f"Failed to search patterns: {e}")
        return {
            "status": "error",
            "message": str(e),
            "query": query
        }


async def _merge_config_sections(
    base_config: Dict[str, Any],
    persona_config: Dict[str, Any],
    inheritance_weight: float
) -> Dict[str, Any]:
    """Merge configuration sections using weighted inheritance.
    
    Args:
        base_config: Base configuration dictionary
        persona_config: Persona configuration dictionary
        inheritance_weight: Weight for base configuration (0.0 to 1.0)
        
    Returns:
        Merged configuration dictionary
    """
    merged = {}
    persona_weight = 1.0 - inheritance_weight
    
    # Get all unique keys from both configs
    all_sections = set(base_config.keys()) | set(persona_config.keys())
    
    for section in all_sections:
        base_section = base_config.get(section, {})
        persona_section = persona_config.get(section, {})
        
        if isinstance(base_section, dict) and isinstance(persona_section, dict):
            # Merge dictionaries recursively
            merged[section] = _merge_dict_weighted(base_section, persona_section, inheritance_weight)
        elif isinstance(base_section, (int, float)) and isinstance(persona_section, (int, float)):
            # Weighted average for numeric values
            merged[section] = base_section * inheritance_weight + persona_section * persona_weight
        elif persona_section:  # Persona takes precedence if it exists
            merged[section] = persona_section
        else:  # Fall back to base
            merged[section] = base_section
    
    # Add inheritance metadata
    merged["_inheritance"] = {
        "base_weight": inheritance_weight,
        "persona_weight": persona_weight,
        "merged_at": datetime.datetime.now().isoformat()
    }
    
    return merged


def _merge_dict_weighted(
    base_dict: Dict[str, Any],
    persona_dict: Dict[str, Any],
    inheritance_weight: float
) -> Dict[str, Any]:
    """Recursively merge dictionaries with weighted inheritance."""
    merged = {}
    all_keys = set(base_dict.keys()) | set(persona_dict.keys())
    
    for key in all_keys:
        base_val = base_dict.get(key)
        persona_val = persona_dict.get(key)
        
        if isinstance(base_val, dict) and isinstance(persona_val, dict):
            # Recursive merge for nested dicts
            merged[key] = _merge_dict_weighted(base_val, persona_val, inheritance_weight)
        elif isinstance(base_val, (int, float)) and isinstance(persona_val, (int, float)):
            # Weighted average for numbers
            persona_weight = 1.0 - inheritance_weight
            merged[key] = base_val * inheritance_weight + persona_val * persona_weight
        elif persona_val is not None:  # Persona value exists
            merged[key] = persona_val
        elif base_val is not None:  # Base value exists
            merged[key] = base_val
    
    return merged


async def main() -> None:
    """Main entry point for Helios MCP server."""
    logger.info("Starting Helios MCP Server...")
    
    # Ensure configuration directories exist
    config.ensure_directories()
    
    # Initialize with sample data if needed
    try:
        await loader.load_base_config()  # This will create default if missing
        logger.info(f"Configuration initialized at {config.base_path.parent}")
    except Exception as e:
        logger.error(f"Failed to initialize configuration: {e}")
        return
    
    logger.info(f"Helios MCP Server ready with {len(mcp.list_tools())} tools")
    
    # Run the FastMCP server
    await mcp.run()


if __name__ == "__main__":
    asyncio.run(main())
