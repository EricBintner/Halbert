"""
Settings management API routes (Phase 11).

Provides REST API for:
- Model configuration (orchestrator/specialist)
- LLM endpoints management
- System preferences
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from pathlib import Path
import yaml
import logging

from ...utils.platform import get_config_dir

logger = logging.getLogger('cerebric.dashboard')

router = APIRouter()


# Pydantic models
class SavedEndpoint(BaseModel):
    """Saved LLM endpoint (without model - model is selected separately)."""
    id: Optional[str] = None  # Auto-generated if not provided
    name: str  # User-friendly name, e.g., "Local Ollama", "Work Server"
    url: str  # e.g., "http://localhost:11434"
    provider: str = "ollama"  # ollama, openai, anthropic
    api_key: Optional[str] = None  # For API-key based providers


class ModelEndpoint(BaseModel):
    """LLM endpoint configuration (legacy, still used for assignments)."""
    endpoint: str  # e.g., "http://localhost:11434"
    provider: str = "ollama"  # ollama, llamacpp, mlx, openai
    model: str  # e.g., "llama3.1:8b-instruct"
    name: str = ""  # User-friendly name
    api_key: Optional[str] = None  # For OpenAI-compatible


class ModelAssignment(BaseModel):
    """Assign a model to a role (guide/specialist/vision)."""
    endpoint_id: str  # ID of the saved endpoint
    model: str  # Model name from that endpoint


class ModelConfigUpdate(BaseModel):
    """Update model routing configuration."""
    orchestrator: Optional[ModelEndpoint] = None
    specialist: Optional[ModelEndpoint] = None
    routing_strategy: Optional[str] = "auto"


class ComputerNameUpdate(BaseModel):
    """Update computer's display name."""
    name: str


@router.get("/model")
async def get_model_settings() -> Dict[str, Any]:
    """Get current model configuration including orchestrator/specialist."""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Default structure
        result = {
            'orchestrator': {
                'endpoint': 'http://localhost:11434',
                'provider': 'ollama',
                'model': 'llama3.1:8b-instruct',
                'name': 'Local Ollama'
            },
            'specialist': {
                'enabled': False,
                'endpoint': '',
                'provider': 'ollama',
                'model': '',
                'name': ''
            },
            'vision': {
                'enabled': False,
                'endpoint': '',
                'provider': 'ollama',
                'model': '',
                'name': ''
            },
            'routing': {
                'strategy': 'auto',
                'prefer_specialist_for': ['code_generation', 'code_analysis', 'system_command']
            },
            'saved_endpoints': []
        }
        
        # Merge with actual config
        if 'orchestrator' in config:
            result['orchestrator'].update(config['orchestrator'])
        if 'specialist' in config:
            result['specialist'].update(config['specialist'])
        if 'vision' in config:
            result['vision'].update(config['vision'])
        if 'routing' in config:
            result['routing'].update(config['routing'])
        if 'saved_endpoints' in config:
            import uuid
            # Ensure all endpoints have IDs and mask API keys
            endpoints = []
            needs_save = False
            for ep in config['saved_endpoints']:
                ep_copy = ep.copy()
                # Generate ID for legacy endpoints that don't have one
                if not ep_copy.get('id'):
                    ep_copy['id'] = str(uuid.uuid4())[:8]
                    ep['id'] = ep_copy['id']  # Update original too
                    needs_save = True
                # Migrate 'endpoint' field to 'url' (legacy -> new)
                if not ep_copy.get('url') and ep_copy.get('endpoint'):
                    ep_copy['url'] = ep_copy['endpoint']
                    ep['url'] = ep_copy['url']
                    needs_save = True
                if ep_copy.get('api_key'):
                    ep_copy['api_key'] = '***'
                endpoints.append(ep_copy)
            
            # Save back if we added IDs
            if needs_save:
                with open(config_path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False)
            
            result['saved_endpoints'] = endpoints
        
        return result
    
    except Exception as e:
        logger.error(f"Error getting model settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model")
async def update_model_settings(update: ModelConfigUpdate) -> Dict[str, Any]:
    """Update model configuration."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Apply updates
        if update.orchestrator:
            config['orchestrator'] = {
                'endpoint': update.orchestrator.endpoint,
                'provider': update.orchestrator.provider,
                'model': update.orchestrator.model,
                'name': update.orchestrator.name,
                'always_loaded': True
            }
        
        if update.specialist:
            config['specialist'] = {
                'enabled': True,
                'endpoint': update.specialist.endpoint,
                'provider': update.specialist.provider,
                'model': update.specialist.model,
                'name': update.specialist.name,
                'load_strategy': 'on_demand'
            }
        
        if update.routing_strategy:
            if 'routing' not in config:
                config['routing'] = {}
            config['routing']['strategy'] = update.routing_strategy
        
        # Save
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Model config updated: {config_path}")
        
        return {'success': True, 'config': config}
    
    except Exception as e:
        logger.error(f"Error updating model settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/status")
async def get_model_status() -> Dict[str, Any]:
    """
    Get LLM connection status and model availability.
    
    Auto-configures Local Ollama if detected but not yet configured.
    
    Returns:
        - ollama_connected: Whether Ollama server is reachable
        - model_installed: Whether the configured model is installed
        - model_name: The configured model name
        - available_models: List of installed models
        - auto_configured: True if we just auto-configured Ollama
    """
    import httpx
    
    # Get config
    config_path = get_config_dir() / 'models.yml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    
    orchestrator = config.get('orchestrator', {})
    saved_endpoints = config.get('saved_endpoints', [])
    providers = config.get('providers', {})
    
    # Determine endpoint to check - try multiple sources:
    # 1. orchestrator.endpoint
    # 2. providers.ollama.base_url  
    # 3. first saved endpoint url
    # 4. default localhost
    endpoint = orchestrator.get('endpoint')
    if not endpoint:
        endpoint = providers.get('ollama', {}).get('base_url')
    if not endpoint and saved_endpoints:
        endpoint = saved_endpoints[0].get('url', 'http://localhost:11434')
    if not endpoint:
        endpoint = 'http://localhost:11434'
    
    model = orchestrator.get('model', '')
    
    # Check if this is a fresh install (no orchestrator configured and no saved endpoints)
    is_fresh_install = not orchestrator.get('model') and len(saved_endpoints) == 0
    
    result = {
        'ollama_connected': False,
        'model_installed': False,
        'model_name': model,
        'endpoint': endpoint,
        'available_models': [],
        'recommended_model': None,
        'auto_configured': False
    }
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{endpoint}/api/tags")
            if response.status_code == 200:
                result['ollama_connected'] = True
                data = response.json()
                models = [m['name'] for m in data.get('models', [])]
                result['available_models'] = models
                
                # Auto-create Local Ollama saved endpoint if fresh install
                # (User still needs to select the model themselves)
                if is_fresh_install and models:
                    import uuid
                    # Only create the saved endpoint, don't auto-set Guide model
                    # Use 'url' field and include 'id' to match frontend SavedEndpoint interface
                    config['saved_endpoints'] = [{
                        'id': str(uuid.uuid4())[:8],
                        'name': 'Local Ollama',
                        'url': 'http://localhost:11434',
                        'provider': 'ollama',
                        'api_key': ''
                    }]
                    
                    # Save the endpoint configuration
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(config_path, 'w') as f:
                        yaml.dump(config, f, default_flow_style=False)
                    
                    logger.info("Auto-created Local Ollama saved endpoint")
                    result['auto_configured'] = True
                    
                    # Set recommended model for UI to suggest
                    preferred = ['llama3.1:8b', 'llama3.2:3b', 'llama3.1:8b-instruct', 'mistral:7b', 'qwen2.5:7b']
                    for pref in preferred:
                        if pref in models:
                            result['recommended_model'] = pref
                            break
                    if not result['recommended_model']:
                        result['recommended_model'] = models[0]
                
                # Check if configured model is installed
                result['model_installed'] = model and model in models
                
                # Recommend a model if none configured or configured not available
                if models and (not model or model not in models):
                    preferred = ['llama3.1:8b', 'llama3.2:3b', 'mistral:7b', 'qwen2.5:7b']
                    for pref in preferred:
                        if pref in models:
                            result['recommended_model'] = pref
                            break
                    if not result['recommended_model']:
                        result['recommended_model'] = models[0]
                        
    except Exception as e:
        logger.warning(f"Ollama connection check failed: {e}")
    
    return result


@router.post("/model/install")
async def install_model(model_name: str = "llama3.1:8b") -> Dict[str, Any]:
    """
    Install a model via Ollama pull.
    
    This is a quick operation that starts the pull - Ollama handles
    the actual download in the background.
    """
    import httpx
    
    # Get endpoint from config
    config_path = get_config_dir() / 'models.yml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}
    
    endpoint = config.get('orchestrator', {}).get('endpoint', 'http://localhost:11434')
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for pull
            response = await client.post(
                f"{endpoint}/api/pull",
                json={"name": model_name, "stream": False}
            )
            
            if response.status_code == 200:
                # Update config to use this model
                if 'orchestrator' not in config:
                    config['orchestrator'] = {}
                config['orchestrator']['model'] = model_name
                config['orchestrator']['provider'] = 'ollama'
                config['orchestrator']['always_loaded'] = True
                
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False)
                
                logger.info(f"Model {model_name} installed successfully")
                return {
                    'success': True,
                    'message': f'Model {model_name} installed successfully!',
                    'model': model_name
                }
            else:
                return {
                    'success': False,
                    'message': f'Pull failed: HTTP {response.status_code}'
                }
    except httpx.TimeoutException:
        return {
            'success': False,
            'message': 'Download timed out - model may still be downloading in background'
        }
    except Exception as e:
        logger.error(f"Model install failed: {e}")
        return {
            'success': False,
            'message': str(e)
        }


@router.post("/model/test")
async def test_model_endpoint(endpoint: ModelEndpoint) -> Dict[str, Any]:
    """Test connectivity to a model endpoint."""
    try:
        import httpx
        
        # Build test URL based on provider
        if endpoint.provider == 'ollama':
            test_url = f"{endpoint.endpoint}/api/tags"
        elif endpoint.provider == 'openai':
            test_url = f"{endpoint.endpoint}/v1/models"
        else:
            test_url = f"{endpoint.endpoint}/health"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {}
            if endpoint.api_key:
                headers['Authorization'] = f'Bearer {endpoint.api_key}'
            
            response = await client.get(test_url, headers=headers)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': f'Connected to {endpoint.endpoint}',
                    'models_available': True
                }
            else:
                return {
                    'success': False,
                    'message': f'HTTP {response.status_code}',
                    'models_available': False
                }
    
    except httpx.TimeoutException:
        return {
            'success': False,
            'message': 'Connection timed out',
            'models_available': False
        }
    except Exception as e:
        return {
            'success': False,
            'message': str(e),
            'models_available': False
        }


@router.get("/endpoints")
async def list_saved_endpoints() -> List[Dict[str, Any]]:
    """Get list of saved endpoints (without models)."""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            endpoints = config.get('saved_endpoints', [])
            # Mask API keys in response
            for ep in endpoints:
                if ep.get('api_key'):
                    ep['api_key'] = '***'
            return endpoints
        
        return []
    
    except Exception as e:
        logger.error(f"Error listing endpoints: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/endpoints")
async def save_endpoint(endpoint: SavedEndpoint) -> Dict[str, Any]:
    """Save an endpoint (name, URL, provider, optional API key - no model)."""
    import uuid
    
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        if 'saved_endpoints' not in config:
            config['saved_endpoints'] = []
        
        # Generate ID if not provided
        ep_dict = endpoint.dict()
        if not ep_dict.get('id'):
            ep_dict['id'] = str(uuid.uuid4())[:8]
        
        # Check for existing endpoint by ID
        existing_idx = None
        existing_ep = None
        for i, e in enumerate(config['saved_endpoints']):
            if e.get('id') == ep_dict['id']:
                existing_idx = i
                existing_ep = e
                break
        
        if existing_idx is None:
            # New endpoint
            config['saved_endpoints'].append(ep_dict)
        else:
            # Update existing - preserve API key if masked
            if ep_dict.get('api_key') == '***' and existing_ep:
                ep_dict['api_key'] = existing_ep.get('api_key')
            config['saved_endpoints'][existing_idx] = ep_dict
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        # Mask API key in response
        response_ep = ep_dict.copy()
        if response_ep.get('api_key'):
            response_ep['api_key'] = '***'
        
        return {'success': True, 'endpoint': response_ep, 'endpoints': config['saved_endpoints']}
    
    except Exception as e:
        logger.error(f"Error saving endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/endpoints/{endpoint_id}/models")
async def list_endpoint_models(endpoint_id: str) -> Dict[str, Any]:
    """Fetch available models from a specific endpoint."""
    import httpx
    
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="No endpoints configured")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        # Find the endpoint
        endpoint = None
        for ep in config.get('saved_endpoints', []):
            if ep.get('id') == endpoint_id:
                endpoint = ep
                break
        
        if not endpoint:
            raise HTTPException(status_code=404, detail=f"Endpoint {endpoint_id} not found")
        
        # Handle both 'url' (new) and 'endpoint' (legacy) field names
        url = endpoint.get('url') or endpoint.get('endpoint', '')
        provider = endpoint.get('provider', 'ollama')
        api_key = endpoint.get('api_key')
        
        models = []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            
            if provider == 'ollama':
                response = await client.get(f"{url}/api/tags", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = [m['name'] for m in data.get('models', [])]
            elif provider == 'openai':
                response = await client.get(f"{url}/v1/models", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = [m['id'] for m in data.get('data', [])]
            else:
                # Generic - try common endpoints
                try:
                    response = await client.get(f"{url}/api/tags", headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        models = [m['name'] for m in data.get('models', [])]
                except:
                    pass
        
        return {
            'endpoint_id': endpoint_id,
            'endpoint_name': endpoint.get('name', ''),
            'models': models,
            'count': len(models)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching models from endpoint: {e}")
        return {
            'endpoint_id': endpoint_id,
            'models': [],
            'error': str(e)
        }


@router.post("/endpoints/{endpoint_id}/test")
async def test_endpoint(endpoint_id: str) -> Dict[str, Any]:
    """Test connectivity to a saved endpoint."""
    import httpx
    
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if not config_path.exists():
            return {'success': False, 'message': 'No endpoints configured'}
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        # Find the endpoint
        endpoint = None
        for ep in config.get('saved_endpoints', []):
            if ep.get('id') == endpoint_id:
                endpoint = ep
                break
        
        if not endpoint:
            return {'success': False, 'message': f'Endpoint {endpoint_id} not found'}
        
        url = endpoint.get('url', '')
        provider = endpoint.get('provider', 'ollama')
        api_key = endpoint.get('api_key')
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            
            if provider == 'ollama':
                test_url = f"{url}/api/tags"
            elif provider == 'openai':
                test_url = f"{url}/v1/models"
            else:
                test_url = f"{url}/api/tags"
            
            response = await client.get(test_url, headers=headers)
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': f'Connected to {endpoint.get("name", url)}',
                    'status_code': 200
                }
            else:
                return {
                    'success': False,
                    'message': f'HTTP {response.status_code}',
                    'status_code': response.status_code
                }
    
    except httpx.TimeoutException:
        return {'success': False, 'message': 'Connection timed out'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str) -> Dict[str, Any]:
    """Delete a saved endpoint by ID."""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if not config_path.exists():
            return {'success': True, 'endpoints': []}
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        endpoints = config.get('saved_endpoints', [])
        original_count = len(endpoints)
        config['saved_endpoints'] = [e for e in endpoints if e.get('id') != endpoint_id]
        
        if len(config['saved_endpoints']) == original_count:
            return {'success': False, 'message': f'Endpoint {endpoint_id} not found'}
        
        # Clear any model assignments using this endpoint
        for role in ['orchestrator', 'specialist', 'vision']:
            if config.get(role, {}).get('endpoint_id') == endpoint_id:
                config[role] = {'enabled': False} if role != 'orchestrator' else {}
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return {'success': True, 'deleted': endpoint_id, 'endpoints': config['saved_endpoints']}
    
    except Exception as e:
        logger.error(f"Error deleting endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_endpoint_by_id(config: dict, endpoint_id: str) -> Optional[dict]:
    """Helper to find an endpoint by ID."""
    for ep in config.get('saved_endpoints', []):
        if ep.get('id') == endpoint_id:
            return ep
    return None


@router.post("/assign/guide")
async def assign_guide_model(assignment: ModelAssignment) -> Dict[str, Any]:
    """Assign a model from an endpoint as the guide/orchestrator."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Find the endpoint
        endpoint = _get_endpoint_by_id(config, assignment.endpoint_id)
        if not endpoint:
            raise HTTPException(status_code=404, detail=f"Endpoint {assignment.endpoint_id} not found")
        
        # Update orchestrator/guide configuration
        config['orchestrator'] = {
            'endpoint_id': assignment.endpoint_id,
            'endpoint': endpoint.get('url', ''),
            'provider': endpoint.get('provider', 'ollama'),
            'model': assignment.model,
            'name': endpoint.get('name', ''),
            'always_loaded': True
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Guide model set to {assignment.model} at {endpoint.get('name', endpoint.get('url'))}")
        
        return {
            'success': True, 
            'orchestrator': config['orchestrator'],
            'message': f'Guide model set to {assignment.model}'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting guide: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assign/specialist")
async def assign_specialist_model(assignment: ModelAssignment) -> Dict[str, Any]:
    """Assign a model from an endpoint as the specialist/coder."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Find the endpoint
        endpoint = _get_endpoint_by_id(config, assignment.endpoint_id)
        if not endpoint:
            raise HTTPException(status_code=404, detail=f"Endpoint {assignment.endpoint_id} not found")
        
        # Update specialist configuration
        config['specialist'] = {
            'enabled': True,
            'endpoint_id': assignment.endpoint_id,
            'endpoint': endpoint.get('url', ''),
            'provider': endpoint.get('provider', 'ollama'),
            'model': assignment.model,
            'name': endpoint.get('name', ''),
            'load_strategy': 'on_demand'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Specialist model set to {assignment.model} at {endpoint.get('name', endpoint.get('url'))}")
        
        return {
            'success': True, 
            'specialist': config['specialist'],
            'message': f'Specialist model set to {assignment.model}'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting specialist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Keep legacy route for backwards compatibility
@router.post("/endpoints/use-as-guide")
async def use_endpoint_as_guide(endpoint: ModelEndpoint) -> Dict[str, Any]:
    """DEPRECATED: Use /assign/guide instead. Set a saved endpoint as the guide/orchestrator model."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        config['orchestrator'] = {
            'endpoint': endpoint.endpoint,
            'provider': endpoint.provider,
            'model': endpoint.model,
            'name': endpoint.name,
            'always_loaded': True
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return {'success': True, 'orchestrator': config['orchestrator'], 'message': f'Guide model set to {endpoint.model}'}
    
    except Exception as e:
        logger.error(f"Error setting guide: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/endpoints/use-as-specialist")
async def use_endpoint_as_specialist(endpoint: ModelEndpoint) -> Dict[str, Any]:
    """DEPRECATED: Use /assign/specialist instead."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        config['specialist'] = {
            'enabled': True,
            'endpoint': endpoint.endpoint,
            'provider': endpoint.provider,
            'model': endpoint.model,
            'name': endpoint.name,
            'load_strategy': 'on_demand'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return {'success': True, 'specialist': config['specialist'], 'message': f'Specialist model set to {endpoint.model}'}
    
    except Exception as e:
        logger.error(f"Error setting specialist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/specialist/clear")
async def clear_specialist() -> Dict[str, Any]:
    """Clear the specialist model configuration."""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Reset specialist to disabled
        config['specialist'] = {
            'enabled': False,
            'endpoint': '',
            'provider': 'ollama',
            'model': '',
            'name': '',
            'load_strategy': 'on_demand'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info("Specialist model cleared")
        
        return {'success': True, 'message': 'Specialist cleared'}
    
    except Exception as e:
        logger.error(f"Error clearing specialist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assign/vision")
async def assign_vision_model(assignment: ModelAssignment) -> Dict[str, Any]:
    """Assign a model from an endpoint as the vision model."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Find the endpoint
        endpoint = _get_endpoint_by_id(config, assignment.endpoint_id)
        if not endpoint:
            raise HTTPException(status_code=404, detail=f"Endpoint {assignment.endpoint_id} not found")
        
        # Update vision configuration
        config['vision'] = {
            'enabled': True,
            'endpoint_id': assignment.endpoint_id,
            'endpoint': endpoint.get('url', ''),
            'provider': endpoint.get('provider', 'ollama'),
            'model': assignment.model,
            'name': endpoint.get('name', ''),
            'load_strategy': 'on_demand'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Vision model set to {assignment.model} at {endpoint.get('name', endpoint.get('url'))}")
        
        return {
            'success': True, 
            'vision': config['vision'],
            'message': f'Vision model set to {assignment.model}'
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting vision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/guide/clear")
async def clear_guide() -> Dict[str, Any]:
    """Clear the guide/orchestrator model configuration."""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        config['orchestrator'] = {
            'endpoint': '',
            'provider': 'ollama',
            'model': '',
            'name': '',
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info("Guide model cleared")
        
        return {'success': True, 'message': 'Guide model cleared'}
    
    except Exception as e:
        logger.error(f"Error clearing guide: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy route for backwards compatibility
@router.post("/endpoints/use-as-vision")
async def use_endpoint_as_vision(endpoint: ModelEndpoint) -> Dict[str, Any]:
    """DEPRECATED: Use /assign/vision instead."""
    try:
        config_path = get_config_dir() / 'models.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        config['vision'] = {
            'enabled': True,
            'endpoint': endpoint.endpoint,
            'provider': endpoint.provider,
            'model': endpoint.model,
            'name': endpoint.name,
            'load_strategy': 'on_demand'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return {'success': True, 'vision': config['vision'], 'message': f'Vision model set to {endpoint.model}'}
    
    except Exception as e:
        logger.error(f"Error setting vision model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vision/clear")
async def clear_vision() -> Dict[str, Any]:
    """Clear the vision model configuration."""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # Reset vision to disabled
        config['vision'] = {
            'enabled': False,
            'endpoint': '',
            'provider': 'ollama',
            'model': '',
            'name': '',
            'load_strategy': 'on_demand'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info("Vision model cleared")
        
        return {'success': True, 'message': 'Vision model cleared'}
    
    except Exception as e:
        logger.error(f"Error clearing vision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/endpoints")
async def delete_endpoint_legacy(endpoint_url: str, model: str = None) -> Dict[str, Any]:
    """Delete a saved endpoint by URL and optionally model name. (Legacy - use DELETE /endpoints/{id} instead)"""
    try:
        config_path = get_config_dir() / 'models.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        else:
            return {'success': True, 'endpoints': []}
        
        # Remove matching endpoint (by URL + model if specified, else just URL)
        endpoints = config.get('saved_endpoints', [])
        if model:
            # Match both URL and model for precise deletion
            config['saved_endpoints'] = [
                e for e in endpoints 
                if not (e.get('endpoint') == endpoint_url and e.get('model') == model)
            ]
        else:
            # Legacy: match just URL (remove first match only to avoid mass deletion)
            new_endpoints = []
            found = False
            for e in endpoints:
                if e.get('endpoint') == endpoint_url and not found:
                    found = True  # Skip first match
                else:
                    new_endpoints.append(e)
            config['saved_endpoints'] = new_endpoints
        
        # Clear specialist if it matched the deleted endpoint
        specialist = config.get('specialist', {})
        if specialist.get('endpoint') == endpoint_url:
            if not model or specialist.get('model') == model:
                config['specialist'] = {'enabled': False}
                logger.info("Cleared specialist config (endpoint was deleted)")
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return {'success': True, 'endpoints': config['saved_endpoints']}
    
    except Exception as e:
        logger.error(f"Error deleting endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/persona-names")
async def get_persona_names() -> Dict[str, Any]:
    """Get the AI name and user preferences from onboarding.
    
    Name priority:
    1. ai_name from preferences (set during onboarding)
    2. System hostname
    3. "Cerebric" (app default)
    """
    import socket
    
    try:
        config_path = get_config_dir() / 'preferences.yml'
        
        # Get system hostname as fallback
        try:
            hostname = socket.gethostname()
        except:
            hostname = None
        
        # Default result - use hostname or app name
        result = {
            'ai_name': hostname or 'Cerebric',
            'user_name': None,
            'user_type': None,
            'names': {}  # Deprecated but kept for backwards compatibility
        }
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
            
            # Priority: ai_name > hostname > "Cerebric"
            if prefs.get('ai_name'):
                result['ai_name'] = prefs['ai_name']
            
            if prefs.get('user_name'):
                result['user_name'] = prefs['user_name']
            if prefs.get('user_type'):
                result['user_type'] = prefs['user_type']
        
        return result
    
    except Exception as e:
        logger.error(f"Error getting persona names: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PersonaNameUpdate(BaseModel):
    persona: str
    name: str


# ─────────────────────────────────────────────────────────────────────────────
# Custom AI Rules - User-defined guardrails for edge cases
# ─────────────────────────────────────────────────────────────────────────────

class AIRule(BaseModel):
    """A custom rule to guide AI behavior."""
    id: Optional[str] = None
    rule: str  # The rule text, e.g., "bcachefs requires kernel 6.8 or earlier"
    category: str = "general"  # general, storage, network, security, kernel, etc.
    priority: str = "high"  # high, medium, low - high rules are always included
    enabled: bool = True
    created_at: Optional[str] = None


@router.get("/ai-rules")
async def get_ai_rules() -> Dict[str, Any]:
    """Get all custom AI rules."""
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            return {
                'rules': data.get('rules', []),
                'last_updated': data.get('last_updated')
            }
        
        # Return empty with example structure
        return {
            'rules': [],
            'last_updated': None,
            'examples': [
                "bcachefs requires kernel 6.8 or earlier - do not recommend kernel upgrades",
                "This system uses ZFS on root - grub-install requires special handling",
                "Docker storage is on /data/docker, not default location",
                "Always use 'apt' not 'apt-get' for package management suggestions",
            ]
        }
    
    except Exception as e:
        logger.error(f"Error getting AI rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-rules")
async def add_ai_rule(rule: AIRule) -> Dict[str, Any]:
    """Add a new custom AI rule."""
    import uuid
    
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {'rules': []}
        
        # Generate ID and timestamp
        new_rule = {
            'id': rule.id or str(uuid.uuid4())[:8],
            'rule': rule.rule,
            'category': rule.category,
            'priority': rule.priority,
            'enabled': rule.enabled,
            'created_at': rule.created_at or datetime.now().isoformat(),
        }
        
        data.setdefault('rules', []).append(new_rule)
        data['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Added AI rule: {rule.rule[:50]}...")
        return {'success': True, 'rule': new_rule}
    
    except Exception as e:
        logger.error(f"Error adding AI rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ai-rules/{rule_id}")
async def delete_ai_rule(rule_id: str) -> Dict[str, Any]:
    """Delete a custom AI rule."""
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="No rules found")
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        rules = data.get('rules', [])
        original_count = len(rules)
        data['rules'] = [r for r in rules if r.get('id') != rule_id]
        
        if len(data['rules']) == original_count:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        
        data['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Deleted AI rule: {rule_id}")
        return {'success': True, 'deleted': rule_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting AI rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ai-rules/{rule_id}")
async def update_ai_rule(rule_id: str, rule: AIRule) -> Dict[str, Any]:
    """Update an existing AI rule."""
    try:
        config_path = get_config_dir() / 'ai_rules.yml'
        
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="No rules found")
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        rules = data.get('rules', [])
        updated = False
        
        for i, r in enumerate(rules):
            if r.get('id') == rule_id:
                rules[i] = {
                    'id': rule_id,
                    'rule': rule.rule,
                    'category': rule.category,
                    'priority': rule.priority,
                    'enabled': rule.enabled,
                    'created_at': r.get('created_at', datetime.now().isoformat()),
                }
                updated = True
                break
        
        if not updated:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        
        data['rules'] = rules
        data['last_updated'] = datetime.now().isoformat()
        
        with open(config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Updated AI rule: {rule_id}")
        return {'success': True, 'rule': rules[i]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating AI rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persona-name")
async def set_persona_name(update: PersonaNameUpdate) -> Dict[str, Any]:
    """Set the AI name for a specific persona."""
    try:
        config_path = get_config_dir() / 'preferences.yml'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
        else:
            prefs = {}
        
        if 'persona_names' not in prefs:
            prefs['persona_names'] = {
                'it_admin': 'Cerebric',
                'friend': 'Cera',
                'casual': 'Cera',
                'custom': 'Assistant'
            }
        
        prefs['persona_names'][update.persona] = update.name
        
        with open(config_path, 'w') as f:
            yaml.dump(prefs, f, default_flow_style=False)
        
        logger.info(f"Persona '{update.persona}' name set to: {update.name}")
        return {'success': True, 'persona': update.persona, 'name': update.name}
    
    except Exception as e:
        logger.error(f"Error setting persona name: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Keep old endpoint for backwards compatibility
@router.get("/computer-name")
async def get_computer_name() -> Dict[str, str]:
    """DEPRECATED: Use /persona-names instead. Get the default AI name."""
    try:
        config_path = get_config_dir() / 'preferences.yml'
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
            # Return the active persona's name or fallback
            persona_names = prefs.get('persona_names', {})
            return {'name': persona_names.get('it_admin', 'Cerebric')}
        
        return {'name': 'Cerebric'}
    
    except Exception as e:
        logger.error(f"Error getting computer name: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts")
async def get_prompt_settings() -> Dict[str, Any]:
    """Get current prompt configuration."""
    try:
        from ...model.prompt_manager import PromptManager, PromptMode
        
        manager = PromptManager()
        
        # Get all mode descriptions
        modes = {}
        for mode in PromptMode:
            modes[mode.value] = manager.get_mode_description(mode)
        
        return {
            'base_safety_prompt': manager.BASE_SAFETY_PROMPT[:200] + '...',  # Preview
            'modes': modes
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# System Profile (Phase 14: Self-Awareness)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/system-profile")
async def get_system_profile() -> Dict[str, Any]:
    """Get the current system profile (cached or from disk)."""
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        
        # Try to load from disk if not already scanned
        if not profiler.profile:
            profiler.load_profile()
        
        if profiler.profile:
            return {
                "status": "loaded",
                "profile": profiler.profile,
                "summary": profiler.get_summary(),
            }
        else:
            return {
                "status": "not_scanned",
                "message": "No system profile available. Run POST /api/settings/system-profile/scan to create one.",
            }
    
    except Exception as e:
        logger.error(f"Error getting system profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-profile/scan")
async def scan_system_profile() -> Dict[str, Any]:
    """Run a comprehensive system profile scan."""
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        
        logger.info("Starting system profile scan...")
        profile = profiler.scan_all()
        
        # Save to disk for persistence
        save_path = profiler.save_profile()
        
        return {
            "status": "complete",
            "profile": profile,
            "summary": profiler.get_summary(),
            "saved_to": str(save_path),
        }
    
    except Exception as e:
        logger.error(f"Error scanning system profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-profile/summary")
async def get_system_profile_summary() -> Dict[str, Any]:
    """Get just the human-readable system summary (for chat context)."""
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        
        # Try to load if not available
        if not profiler.profile:
            profiler.load_profile()
        
        if not profiler.profile:
            # Quick scan if no profile exists
            profiler.scan_all()
            profiler.save_profile()
        
        return {
            "summary": profiler.get_summary(),
            "scan_time": profiler.profile.get("scan_time"),
        }
    
    except Exception as e:
        logger.error(f"Error getting system summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-profile/quick-scan")
async def quick_scan_system() -> Dict[str, Any]:
    """
    Run a quick scan of frequently-changing items.
    
    Used on app startup. Takes 2-5 seconds.
    Updates: services, storage, network, containers, memory, uptime.
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        profile = profiler.quick_scan()
        
        return {
            "status": "complete",
            "scan_type": "quick",
            "profile": profile,
            "summary": profiler.get_summary(),
        }
    
    except Exception as e:
        logger.error(f"Error running quick scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system-profile/scan-category/{category}")
async def scan_category(category: str) -> Dict[str, Any]:
    """
    Scan a specific category (for page rescans).
    
    Categories: storage, services, network, packages, security, 
                containers, users, hardware, os, kernel, boot,
                development, desktop, scheduled_tasks, virtualization
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        profiler = get_system_profiler()
        result = profiler.scan_category(category)
        
        return {
            "status": "complete",
            "category": category,
            "data": result,
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error scanning category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_system_metrics() -> Dict[str, Any]:
    """
    Get real-time system metrics (CPU, memory, uptime).
    
    This provides a web fallback when Tauri is not available.
    """
    import psutil
    import time
    
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Memory
        mem = psutil.virtual_memory()
        memory_percent = mem.percent
        memory_total_gb = mem.total / (1024**3)
        memory_available_gb = mem.available / (1024**3)
        memory_used_gb = mem.used / (1024**3)
        
        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        
        # Disks
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "mount_point": partition.mountpoint,
                    "fs_type": partition.fstype,
                    "total_gb": usage.total / (1024**3),
                    "used_gb": usage.used / (1024**3),
                    "available_gb": usage.free / (1024**3),
                    "usage_percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_total_gb": round(memory_total_gb, 1),
            "memory_available_gb": round(memory_available_gb, 1),
            "memory_used_gb": round(memory_used_gb, 1),
            "uptime_seconds": uptime_seconds,
            "disks": disks,
        }
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/onboarding/status")
async def get_onboarding_status() -> Dict[str, Any]:
    """
    Check if onboarding is complete.
    
    Returns whether the user has completed first-time setup.
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        from ...utils.platform import get_data_dir
        import socket
        
        config_dir = get_config_dir()
        data_dir = get_data_dir()
        onboarding_file = config_dir / "onboarding_complete"
        profile_file = data_dir / "system_profile.json"  # Profile is in data_dir, not config_dir
        
        # Check if onboarding was completed
        is_complete = onboarding_file.exists() and profile_file.exists()
        
        # Get hostname for prefill
        hostname = socket.gethostname()
        
        # Check if profile exists
        profiler = get_system_profiler()
        has_profile = profiler.load_profile() is not None
        
        return {
            "onboarding_complete": is_complete,
            "has_system_profile": has_profile,
            "suggested_name": hostname,
            "last_deep_scan": profiler.profile.get("scan_time") if profiler.profile else None,
            "last_quick_scan": profiler.profile.get("quick_scan_time") if profiler.profile else None,
        }
    
    except Exception as e:
        logger.error(f"Error checking onboarding status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class OnboardingData(BaseModel):
    """Onboarding configuration."""
    computer_name: str
    admin_name: str = "Admin"  # IT Admin/user's name
    user_type: str = "casual"  # casual, it_admin, developer, ai_professional


@router.post("/onboarding/complete")
async def complete_onboarding(data: OnboardingData) -> Dict[str, Any]:
    """
    Complete the onboarding process.
    
    1. Run deep system scan
    2. Save computer name and user type
    3. Mark onboarding as complete
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        
        logger.info(f"Starting onboarding for {data.computer_name} ({data.user_type})")
        
        # Run deep scan
        profiler = get_system_profiler()
        profile = profiler.scan_all()
        
        # Add user preferences to profile
        profile["user_settings"] = {
            "computer_name": data.computer_name,
            "admin_name": data.admin_name,
            "user_type": data.user_type,
            "onboarding_date": datetime.now().isoformat() if 'datetime' in dir() else None,
        }
        
        # Save profile
        profiler.save_profile()
        
        # Mark onboarding complete
        config_dir = get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        
        onboarding_file = config_dir / "onboarding_complete"
        onboarding_file.write_text(f"{data.computer_name}\n{data.admin_name}\n{data.user_type}")
        
        # Save to preferences.yml so chat can read the AI name and user name
        preferences_path = config_dir / "preferences.yml"
        try:
            if preferences_path.exists():
                with open(preferences_path) as f:
                    prefs = yaml.safe_load(f) or {}
            else:
                prefs = {}
            
            # Set the AI name from onboarding (this is the "computer name" the user chose)
            prefs["ai_name"] = data.computer_name
            prefs["user_name"] = data.admin_name
            prefs["user_type"] = data.user_type
            
            # Remove deprecated persona_names if present
            prefs.pop("persona_names", None)
            prefs.pop("computer_name", None)  # Use ai_name instead
            
            with open(preferences_path, 'w') as f:
                yaml.dump(prefs, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Saved preferences: ai_name={data.computer_name}, user_name={data.admin_name}")
        except Exception as e:
            logger.warning(f"Failed to save preferences: {e}")
        
        return {
            "status": "complete",
            "computer_name": data.computer_name,
            "user_type": data.user_type,
            "profile_summary": profiler.get_summary(),
        }
    
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Import datetime at module level for onboarding
from datetime import datetime
