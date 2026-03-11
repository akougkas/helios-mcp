"""Helios MCP Server - Configuration management for AI behaviors with performance optimizations."""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import datetime
import time

from fastmcp import FastMCP, Context
from pydantic import Field

from .config import HeliosConfig, ConfigLoader
from .inheritance import create_behavior_merger, InheritanceCalculator
from .git_store import GitStore
from .cache import init_cache, shutdown_cache, get_cache
from .security import (
    validate_persona_name,
    validate_config_domain,
    validate_config_key,
    sanitize_error_message,
    SecurityError,
    PathTraversalError,
    InvalidInputError
)
from .learning import (
    LearningManager,
    LearnBehaviorParams,
    TuneWeightParams,
    RevertLearningParams,
    EvolveBehaviorParams
)

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def create_server(helios_dir: Optional[Path] = None, preload_cache: bool = True) -> FastMCP:
    """Factory function to create configured MCP server with performance optimizations.
    
    Args:
        helios_dir: Path to Helios configuration directory. Defaults to ~/.helios
        preload_cache: Whether to preload configurations for better performance
        
    Returns:
        Configured FastMCP server instance
    """
    start_time = time.time()
    
    # Initialize configuration with custom directory
    if helios_dir is None:
        helios_dir = Path.home() / ".helios"
    
    config = HeliosConfig(
        base_path=helios_dir / "base",
        personas_path=helios_dir / "personas", 
        learned_path=helios_dir / "learned",
        temporary_path=helios_dir / "temporary"
    )
    
    # Ensure configuration directories exist
    config.ensure_directories()
    
    # Initialize performance cache system
    await init_cache()
    
    # Initialize optimized loader with caching
    loader = ConfigLoader(config)
    git_store = GitStore(helios_dir)
    learning_manager = LearningManager(helios_dir)
    
    # Preload configurations for better performance
    if preload_cache:
        logger.info("Preloading configurations into cache...")
        preload_start = time.time()
        
        try:
            async with loader:
                await loader.preload_common_configs()
                preload_time = time.time() - preload_start
                logger.info(f"Configuration preload completed in {preload_time:.2f}s")
        except Exception as e:
            logger.warning(f"Configuration preload failed: {e}")
    
    # Create MCP instance
    mcp = FastMCP("Helios")
    
    # Register tools with closure over config/loader/git_store
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
            # Validate persona name to prevent path traversal
            try:
                validated_name = validate_persona_name(persona_name)
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid persona name '{persona_name}': {e}")
                return {
                    "status": "error",
                    "message": f"Invalid persona name: {sanitize_error_message(e)}",
                    "persona_name": "[INVALID]"
                }
            
            if ctx:
                await ctx.info(f"Loading persona '{validated_name}'...")
            
            persona_config = await loader.load_persona_config(validated_name)
            
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
                    "message": f"Persona '{validated_name}' not found, showing sample structure"
                }
            
            if ctx:
                await ctx.info(f"Successfully loaded persona '{validated_name}'")
            
            return {
                "status": "success",
                "persona": persona_config,
                "path": str(config.personas_path / f"{validated_name}.yaml")
            }
            
        except Exception as e:
            logger.error(f"Failed to load persona: {e}")
            return {
                "status": "error",
                "message": sanitize_error_message(e),
                "persona_name": "[SANITIZED]"
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
            # Validate persona name to prevent path traversal
            try:
                validated_name = validate_persona_name(persona_name)
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid persona name '{persona_name}': {e}")
                return {
                    "status": "error",
                    "message": f"Invalid persona name: {sanitize_error_message(e)}",
                    "persona_name": "[INVALID]"
                }
            
            if ctx:
                await ctx.info(f"Calculating inheritance for persona '{validated_name}'...")
            
            # Load base and persona configs directly using loader
            # Don't call other tools from within tools - use the underlying functions
            base_config = await loader.load_base_config()
            if base_config is None:
                base_config = await loader.create_default_base_config()
            
            persona_config = await loader.load_persona_config(validated_name)
            if persona_config is None:
                # Use sample persona for testing
                persona_config = {
                    "behaviors": {
                        "communication_style": "technical",
                        "response_length": "detailed",
                        "domain_focus": "software_development"
                    },
                    "specialization_level": 2,
                    "learning_rate": 0.1,
                    "version": "1.0"
                }
            
            # Calculate inheritance weight using the real InheritanceCalculator
            base_importance = base_config.get("base_importance", 0.7)
            specialization_level = persona_config.get("specialization_level", 1)
            
            # Create behavior merger with the inheritance parameters
            merger = create_behavior_merger(base_importance, specialization_level)
            
            # Calculate the inheritance weight
            inheritance_weight = merger.calculator.calculate_weight(
                base_importance=base_importance,
                specialization_level=specialization_level
            )
            
            if ctx:
                await ctx.info(f"Calculated inheritance weight: {inheritance_weight:.3f}")
            
            # Merge behaviors using the real BehaviorMerger
            merged_behaviors = merger.merge_behaviors(
                base_config, 
                persona_config,
                inheritance_weight=inheritance_weight
            )
            
            return {
                "status": "success",
                "merged_behaviors": merged_behaviors,
                "calculation": {
                    "base_importance": base_importance,
                    "specialization_level": specialization_level,
                    "inheritance_weight": inheritance_weight,
                    "persona_weight": 1 - inheritance_weight
                },
                "persona_name": validated_name
            }
            
        except Exception as e:
            logger.error(f"Failed to merge behaviors: {e}")
            return {
                "status": "error",
                "message": sanitize_error_message(e),
                "persona_name": "[SANITIZED]"
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
                "repository_path": str(helios_dir)
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
            # Validate input parameters to prevent injection and invalid data
            try:
                validated_domain = validate_config_domain(domain)
                validated_key = validate_config_key(key)
                
                # Validate value length and content
                if not isinstance(value, str):
                    raise InvalidInputError("Value must be a string")
                if len(value) > 1000:
                    raise InvalidInputError("Value too long (max 1000 characters)")
                
            except (SecurityError, InvalidInputError) as e:
                logger.warning(f"Invalid preference update parameters: {e}")
                return {
                    "status": "error",
                    "message": f"Invalid input: {sanitize_error_message(e)}",
                    "preference": "[INVALID]"
                }
            
            if ctx:
                await ctx.info(f"Updating preference {validated_domain}.{validated_key} = {value}")
            
            # Load current base config
            identity_file = config.base_path / "identity.yaml"
            if identity_file.exists():
                base_config = await loader.load_yaml(identity_file)
                config_file = identity_file
            else:
                base_config = await loader.load_base_config()
                config_file = config.base_path / "config.yaml"
            
            # Update the preference using validated parameters
            if validated_domain not in base_config:
                base_config[validated_domain] = {}
            
            # Handle nested keys (e.g., "communication.tone")
            if "." in validated_key:
                keys = validated_key.split(".")
                current = base_config[validated_domain]
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value
            else:
                base_config[validated_domain][validated_key] = value
            
            # Save updated configuration
            await loader.save_yaml(config_file, base_config)
            
            if ctx:
                await ctx.info(f"Successfully updated and saved preference")
            
            return {
                "status": "success",
                "updated": {
                    "domain": validated_domain,
                    "key": validated_key,
                    "value": value
                },
                "config_path": str(config_file)
            }
            
        except Exception as e:
            logger.error(f"Failed to update preference: {e}")
            return {
                "status": "error",
                "message": sanitize_error_message(e),
                "preference": "[SANITIZED]"
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

    # Learning System Tools - Direct configuration evolution
    @mcp.tool(
        description="Learn a new behavior by directly editing persona configuration",
        tags={"learning", "evolution"}
    )
    async def learn_behavior(
        persona: str = Field(description="Name of persona to learn in"),
        key: str = Field(description="Dot-notation key (e.g., 'behaviors.tools.package_manager')"),
        value: Any = Field(description="Value to set (can be string, list, dict, etc.)"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Learn a new behavior - adds mass to the gravitational system.
        
        New behaviors don't erase existing ones but shift the dynamics
        through the inheritance model's weighted calculations.
        
        Args:
            params: Learning parameters with persona, key, and value
            
        Returns:
            Learning result with old and new values
        """
        if ctx:
            await ctx.info(f"Learning behavior: {key} for {persona}")
        
        params = LearnBehaviorParams(persona=persona, key=key, value=value)
        return await learning_manager.learn_behavior(params)
    
    @mcp.tool(
        description="Adjust inheritance weights to shift gravitational dynamics",
        tags={"learning", "tuning"}
    )
    async def tune_weight(
        target: str = Field(description="Target config: 'base' or persona name"),
        parameter: str = Field(description="Parameter to tune: 'base_importance' or 'specialization_level'"),
        value: float = Field(description="New value (0.0-1.0 for base_importance, >=1 for specialization_level)"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Tune inheritance weights - adjust the gravitational pull.
        
        Like adjusting the mass of celestial bodies, changing weights
        shifts how strongly base influences personas.
        
        Args:
            target: Target configuration name
            parameter: Parameter to tune
            value: New value for the parameter
            
        Returns:
            Tuning result with old and new values
        """
        if ctx:
            await ctx.info(f"Tuning {parameter} for {target}")
        
        params = TuneWeightParams(target=target, parameter=parameter, value=value)
        return await learning_manager.tune_weight(params)
    
    @mcp.tool(
        description="Undo recent learning by reverting git commits",
        tags={"learning", "revert"}
    )
    async def revert_learning(
        commits_back: int = Field(default=1, ge=1, le=10, description="Number of commits to revert (1-10)"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Revert recent learning - rewind the gravitational timeline.
        
        Uses git to undo recent behavioral changes, returning the system
        to a previous configuration state.
        
        Args:
            commits_back: Number of commits to undo
            
        Returns:
            Revert result with affected commits
        """
        if ctx:
            await ctx.info(f"Reverting {commits_back} commits")
        
        params = RevertLearningParams(commits_back=commits_back)
        return await learning_manager.revert_learning(params)
    
    @mcp.tool(
        description="Move behaviors between configurations (promotion/demotion)",
        tags={"learning", "evolution"}
    )
    async def evolve_behavior(
        from_config: str = Field(description="Source config: 'base' or persona name"),
        to_config: str = Field(description="Target config: 'base' or persona name"),
        key: str = Field(description="Dot-notation key to move (e.g., 'behaviors.package_manager')"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Evolve behavior between configurations - orbital transfer.
        
        Like a moon moving between planets, behaviors can migrate from
        personas to base or vice versa, changing both gravitational systems.
        
        Args:
            from_config: Source configuration
            to_config: Target configuration
            key: Key to move between configs
            
        Returns:
            Evolution result with migration details
        """
        if ctx:
            await ctx.info(f"Evolving {key} from {from_config} to {to_config}")
        
        params = EvolveBehaviorParams(from_config=from_config, to_config=to_config, key=key)
        return await learning_manager.evolve_behavior(params)

    # Performance monitoring and diagnostics tool
    @mcp.tool(
        description="Get performance statistics and cache metrics for optimization",
        tags={"performance", "diagnostics"}
    )
    async def get_performance_stats(
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Get comprehensive performance statistics and cache metrics.
        
        Returns:
            Dictionary containing cache stats, performance metrics, and system info
        """
        try:
            if ctx:
                await ctx.info("Gathering performance statistics...")
            
            # Get cache statistics
            cache = get_cache()
            cache_stats = cache.stats()
            
            # Get merge statistics if behavior merger exists
            merger = create_behavior_merger()
            merge_stats = merger.get_merge_stats()
            
            # System resource info
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            performance_stats = {
                "cache": cache_stats,
                "inheritance": merge_stats,
                "system": {
                    "memory_usage_mb": memory_info.rss / 1024 / 1024,
                    "cpu_percent": process.cpu_percent(),
                    "open_files": len(process.open_files()),
                    "threads": process.num_threads(),
                },
                "server_info": {
                    "helios_dir": str(helios_dir),
                    "uptime_seconds": time.time() - start_time,
                    "personas_available": len(await loader.list_personas()),
                },
                "recommendations": []
            }
            
            # Add performance recommendations
            if cache_stats["hit_rate"] < 0.5:
                performance_stats["recommendations"].append(
                    "Cache hit rate is low (<50%). Consider preloading common configurations or increasing cache TTL."
                )
            
            if performance_stats["system"]["memory_usage_mb"] > 100:
                performance_stats["recommendations"].append(
                    f"Memory usage is high ({performance_stats['system']['memory_usage_mb']:.1f}MB). Consider reducing cache size or implementing cleanup."
                )
            
            if merge_stats["cache_efficiency"] < 60:
                performance_stats["recommendations"].append(
                    "Inheritance calculation cache efficiency is low. Check for configuration churn or increase cache size."
                )
            
            if ctx:
                await ctx.info(f"Performance report generated - cache hit rate: {cache_stats['hit_rate']:.1%}")
            
            return {
                "status": "success",
                "performance": performance_stats,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    # -------------------------------------------------------------------------
    # Helios v2 — Behavioral Science Tools
    # -------------------------------------------------------------------------

    @mcp.tool(
        description="Get the full behavioral context for a persona as system prompt text (v2)",
        tags={"v2", "behavioral", "context"}
    )
    async def get_behavioral_context(
        persona_name: str = Field(description="Persona name (e.g. 'developer', 'researcher')"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Resolve the full 4-level behavioral hierarchy and render as system prompt text.

        Returns a string ready to inject into any LLM's system prompt. Reflects
        the weighted KL-blend of species → domain → user → session levels.
        """
        try:
            from .hierarchy import IdentityHierarchy
            from .renderer import BehavioralRenderer

            if ctx:
                await ctx.info(f"Resolving behavioral context for '{persona_name}'...")

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)
            renderer = BehavioralRenderer()
            text = renderer.render(profile, persona_name)

            if ctx:
                await ctx.info("Behavioral context rendered successfully")

            return {
                "status": "success",
                "persona": persona_name,
                "behavioral_context": text,
                "observation_count": profile.observation_count,
                "specialization_level": profile.specialization_level,
            }
        except Exception as e:
            logger.error(f"Failed to get behavioral context: {e}")
            return {"status": "error", "message": str(e)}

    @mcp.tool(
        description="Observe a conversation and update the behavioral fingerprint for a persona (v2)",
        tags={"v2", "behavioral", "observation"}
    )
    async def observe_interaction(
        persona_name: str = Field(description="Persona to update observations for"),
        messages: list[Dict[str, Any]] = Field(description="Conversation messages (role+content dicts)"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Feed a conversation into the behavioral observation engine.

        Extracts structural, semantic, decision, and user-signal features from
        messages and updates the persona's observed behavioral distributions.
        Returns current observation count and whether drift threshold is near.
        """
        try:
            from .observer import BehavioralObserver
            from .drift import DriftDetector
            from .hierarchy import IdentityHierarchy

            if ctx:
                await ctx.info(f"Observing {len(messages)} messages for '{persona_name}'...")

            # Use a server-scoped observer (keyed by helios_dir path for isolation)
            observer = BehavioralObserver()
            observer.observe(persona_name, messages)
            count = observer.get_observation_count(persona_name)

            # Quick drift check
            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)
            observed_dists = observer.get_accumulated_distributions(persona_name)
            detector = DriftDetector()
            drift_result = detector.compute_drift(profile.distributions, observed_dists, count)

            if ctx:
                await ctx.info(f"Observation count: {count}, drift: {drift_result.total_drift:.3f}")

            return {
                "status": "success",
                "persona": persona_name,
                "observation_count": count,
                "current_drift": round(drift_result.total_drift, 4),
                "drift_threshold": DriftDetector.TOTAL_THRESHOLD,
                "negotiation_recommended": detector.exceeds_threshold(drift_result),
            }
        except Exception as e:
            logger.error(f"Failed to observe interaction: {e}")
            return {"status": "error", "message": str(e)}

    @mcp.tool(
        description="Get a natural language drift report for a persona — call when negotiation_recommended is true (v2)",
        tags={"v2", "behavioral", "drift"}
    )
    async def get_drift_report(
        persona_name: str = Field(description="Persona to get drift report for"),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Generate a human-readable behavioral drift summary.

        When observe_interaction returns negotiation_recommended=true, call this
        tool to get a natural language explanation of what behavioral changes have
        been observed, with a proposal to update the declared profile.
        """
        try:
            from .observer import BehavioralObserver
            from .drift import DriftDetector
            from .negotiation import NegotiationEngine
            from .hierarchy import IdentityHierarchy

            hierarchy = IdentityHierarchy(helios_dir)
            profile = hierarchy.resolve(persona_name)

            observer = BehavioralObserver()
            count = observer.get_observation_count(persona_name)
            if count == 0:
                return {
                    "status": "no_data",
                    "message": f"No observations recorded yet for '{persona_name}'. "
                               "Use observe_interaction first to build a behavioral fingerprint.",
                }

            observed_dists = observer.get_accumulated_distributions(persona_name)
            detector = DriftDetector()
            drift_result = detector.compute_drift(profile.distributions, observed_dists, count)

            engine = NegotiationEngine()
            proposal = engine.generate_summary(persona_name, profile, observed_dists, drift_result)

            if ctx:
                await ctx.info(f"Drift report: total={drift_result.total_drift:.3f}")

            return {
                "status": "success",
                "persona": persona_name,
                "summary": proposal.summary,
                "per_dimension": proposal.per_dimension_summary,
                "total_drift": round(drift_result.total_drift, 4),
                "exceeds_threshold": drift_result.exceeds_total_threshold,
                "proposed_at": proposal.proposed_at,
            }
        except Exception as e:
            logger.error(f"Failed to generate drift report: {e}")
            return {"status": "error", "message": str(e)}

    @mcp.tool(
        description="Accept or reject a proposed behavioral update for a persona (v2)",
        tags={"v2", "behavioral", "negotiation"}
    )
    async def negotiate_update(
        persona_name: str = Field(description="Persona to update"),
        decision: str = Field(description="'accept' or 'reject'"),
        reason: str = Field(default="", description="Optional reason for rejection"),
        accepted_dimensions: Optional[list[str]] = Field(
            default=None,
            description="Specific dimensions to accept (None = accept all)"
        ),
        ctx: Context = None
    ) -> Dict[str, Any]:
        """Apply or reject a behavioral evolution proposal.

        After reviewing get_drift_report, call this to either commit the observed
        behavioral patterns into the declared profile (accept) or discard them (reject).
        Accepted changes are committed to git — this is a step in the agent's behavioral biography.
        """
        try:
            from .observer import BehavioralObserver
            from .drift import DriftDetector
            from .negotiation import NegotiationEngine
            from .hierarchy import IdentityHierarchy

            engine = NegotiationEngine()

            if decision.lower() == "reject":
                result = engine.reject_update(persona_name, reason or "user rejected", helios_dir)
                if ctx:
                    await ctx.info(f"Behavioral update rejected for '{persona_name}'")
                return result

            if decision.lower() == "accept":
                hierarchy = IdentityHierarchy(helios_dir)
                profile = hierarchy.resolve(persona_name)
                observer = BehavioralObserver()
                observed_dists = observer.get_accumulated_distributions(persona_name)
                count = observer.get_observation_count(persona_name)
                detector = DriftDetector()
                drift_result = detector.compute_drift(profile.distributions, observed_dists, count)
                proposal = engine.generate_summary(
                    persona_name, profile, observed_dists, drift_result
                )
                result = engine.apply_update(
                    persona_name, proposal, helios_dir, accepted_dimensions
                )
                if ctx:
                    await ctx.info(f"Behavioral update applied for '{persona_name}'")
                return result

            return {
                "status": "error",
                "message": f"Unknown decision '{decision}'. Use 'accept' or 'reject'."
            }
        except Exception as e:
            logger.error(f"Failed to negotiate update: {e}")
            return {"status": "error", "message": str(e)}

    # Add server shutdown handler for cleanup
    @mcp.resource(
        uri="helios://shutdown",
        name="Server Shutdown Handler",
        description="Clean shutdown with resource cleanup"
    )
    async def shutdown_handler():
        """Handle graceful server shutdown with resource cleanup."""
        try:
            logger.info("Initiating graceful server shutdown...")
            
            # Clean up cache resources
            await shutdown_cache()
            
            # Clean up atomic operations
            from .atomic_ops import cleanup_resources
            cleanup_resources()
            
            logger.info("Server shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during server shutdown: {e}")

    # Log final startup time and return server
    total_startup_time = time.time() - start_time
    logger.info(
        f"Helios MCP Server created with config at {helios_dir} "
        f"(startup time: {total_startup_time:.2f}s)"
    )
    
    return mcp


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
