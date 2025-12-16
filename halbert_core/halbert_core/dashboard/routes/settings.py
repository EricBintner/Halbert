"""
Settings management API routes (Phase 11).

Provides REST API for:
- Model configuration (orchestrator/specialist)
- LLM endpoints management
- System preferences
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from pathlib import Path
import yaml
import logging

from ...utils.platform import get_config_dir

logger = logging.getLogger('halbert.dashboard')

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
    3. "Halbert" (app default)
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
            'ai_name': hostname or 'Halbert',
            'user_name': None,
            'user_type': None,
            'names': {}  # Deprecated but kept for backwards compatibility
        }
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
            
            # Priority: ai_name > hostname > "Halbert"
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


class ComputerNameUpdate(BaseModel):
    """Update the computer/AI name."""
    ai_name: str
    user_name: Optional[str] = None


@router.post("/computer-name")
async def update_computer_name(data: ComputerNameUpdate) -> Dict[str, Any]:
    """Update the AI name (computer name) in preferences.
    
    This is the name the AI uses to identify itself (e.g., "Linus", "HAL", etc.)
    """
    try:
        config_path = get_config_dir() / 'preferences.yml'
        
        # Load existing preferences
        if config_path.exists():
            with open(config_path, 'r') as f:
                prefs = yaml.safe_load(f) or {}
        else:
            prefs = {}
        
        # Update the AI name
        prefs['ai_name'] = data.ai_name
        if data.user_name:
            prefs['user_name'] = data.user_name
        
        # Save back
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(prefs, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Updated computer name to: {data.ai_name}")
        
        return {
            'success': True,
            'ai_name': data.ai_name,
            'user_name': prefs.get('user_name')
        }
    
    except Exception as e:
        logger.error(f"Error updating computer name: {e}")
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
                'it_admin': 'Halbert',
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
            return {'name': persona_names.get('it_admin', 'Halbert')}
        
        return {'name': 'Halbert'}
    
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
    """Run a comprehensive system profile scan.
    
    This is the "Deep Scan" - it scans:
    1. System profile (hardware, OS, etc.)
    2. All discovery types (storage, services, network, backups, security)
    3. Populates self-knowledge from the profile (Genesis vision)
    """
    try:
        from ...discovery.scanners.system_profile import get_system_profiler
        from ...discovery.engine import get_engine
        from ...knowledge import bootstrap_from_profile
        
        profiler = get_system_profiler()
        
        logger.info("Starting system profile scan...")
        profile = profiler.scan_all()
        
        # Save to disk for persistence
        save_path = profiler.save_profile()
        
        # Also run all discovery scanners (storage, services, network, etc.)
        logger.info("Running discovery scanners...")
        engine = get_engine()
        discoveries = engine.scan_all()
        discovery_count = len(discoveries)
        logger.info(f"Discovery scan complete: {discovery_count} items found")
        
        # Populate self-knowledge from the profile
        # This implements Genesis: "The system's data is its biography"
        logger.info("Populating self-knowledge from profile...")
        knowledge_counts = bootstrap_from_profile(profile)
        total_knowledge = sum(knowledge_counts.values())
        logger.info(f"Self-knowledge populated: {total_knowledge} entries")
        
        return {
            "status": "complete",
            "profile": profile,
            "summary": profiler.get_summary(),
            "saved_to": str(save_path),
            "discoveries_scanned": discovery_count,
            "self_knowledge_added": total_knowledge,
            "knowledge_breakdown": knowledge_counts,
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


# =============================================================================
# Ingestion Service API
# =============================================================================

@router.get("/ingestion/status")
async def get_ingestion_status():
    """Get ingestion service status."""
    try:
        from ...ingestion.service import get_ingestion_service
        service = get_ingestion_service()
        return service.status()
    except Exception as e:
        logger.error(f"Failed to get ingestion status: {e}")
        return {
            "running": False,
            "error": str(e)
        }


@router.post("/ingestion/start")
async def start_ingestion():
    """Start the ingestion service."""
    try:
        from ...ingestion.service import get_ingestion_service
        service = get_ingestion_service()
        success = service.start()
        return {
            "success": success,
            "status": service.status()
        }
    except Exception as e:
        logger.error(f"Failed to start ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingestion/stop")
async def stop_ingestion():
    """Stop the ingestion service."""
    try:
        from ...ingestion.service import get_ingestion_service
        service = get_ingestion_service()
        success = service.stop()
        return {
            "success": success,
            "status": service.status()
        }
    except Exception as e:
        logger.error(f"Failed to stop ingestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Document Indexing API
# =============================================================================

@router.get("/docs/stats")
async def get_docs_stats():
    """Get document index statistics."""
    try:
        from ...rag.document_indexer import get_index_stats
        return get_index_stats()
    except Exception as e:
        logger.error(f"Failed to get doc stats: {e}")
        return {"error": str(e), "linux_docs_count": 0}


@router.post("/docs/index")
async def index_documents(max_docs: int = 1000, source: str = None):
    """
    Index Linux documentation into ChromaDB.
    
    Args:
        max_docs: Maximum documents to index
        source: Specific source to index (None = priority sources)
    """
    try:
        from ...rag.document_indexer import index_documents as do_index, get_default_data_dir
        
        data_dir = get_default_data_dir()
        
        if source:
            # Index specific source
            stats = do_index(
                data_dir=data_dir,
                collection_name="linux_docs",
                max_docs=max_docs,
                sources=[source]
            )
            return {
                "source": source,
                "indexed": stats.indexed_docs,
                "skipped": stats.skipped_docs,
                "errors": stats.errors,
                "duration_s": (stats.completed_at - stats.started_at).total_seconds() if stats.completed_at else 0
            }
        else:
            # Index priority sources
            from ...rag.document_indexer import index_priority_docs
            results = index_priority_docs(max_per_source=max_docs)
            
            total_indexed = sum(s.indexed_docs for s in results.values())
            return {
                "sources_indexed": list(results.keys()),
                "total_indexed": total_indexed,
                "per_source": {k: v.indexed_docs for k, v in results.items()}
            }
    except Exception as e:
        logger.error(f"Failed to index documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/docs/query")
async def query_documents(q: str, k: int = 5):
    """
    Query indexed documents.
    
    Args:
        q: Search query
        k: Number of results
    """
    try:
        from ...rag.document_indexer import query_docs
        results = query_docs(q, k=k)
        return {
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Document query failed: {e}")
        return {"query": q, "results": [], "count": 0, "error": str(e)}


# =============================================================================
# Self-Knowledge API (System Ontology)
# =============================================================================

@router.get("/knowledge/stats")
async def get_knowledge_stats():
    """Get self-knowledge statistics."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        return sk.stats()
    except Exception as e:
        logger.error(f"Failed to get knowledge stats: {e}")
        return {"error": str(e), "total_entries": 0}


@router.get("/knowledge/identity")
async def get_system_identity():
    """Get core system identity."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        return {
            "identity": sk.get_identity(),
            "hardware": [
                {"subject": e.subject, "content": e.content}
                for e in sk.get_by_type(sk._knowledge.get('hardware', {}).get('type') or 
                                       __import__('halbert_core.knowledge', fromlist=['KnowledgeType']).KnowledgeType.HARDWARE)
            ] if sk._knowledge else []
        }
    except Exception as e:
        logger.error(f"Failed to get identity: {e}")
        return {"identity": {}, "error": str(e)}


@router.post("/knowledge/bootstrap")
async def bootstrap_system_identity():
    """Bootstrap system identity from current system state."""
    try:
        from ...knowledge import bootstrap_identity
        identity = bootstrap_identity()
        return {"success": True, "identity": identity}
    except Exception as e:
        logger.error(f"Failed to bootstrap identity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TeachRequest(BaseModel):
    subject: str
    content: str
    rationale: Optional[str] = None
    tags: Optional[List[str]] = None


@router.post("/knowledge/teach")
async def teach_system(request: TeachRequest):
    """
    Teach the system something about itself.
    
    Example:
        POST /api/settings/knowledge/teach
        {
            "subject": "bcachefs pool",
            "content": "The pool uses nvme0n1 and nvme1n1 in RAID1",
            "rationale": "For redundancy on critical data",
            "tags": ["storage", "bcachefs"]
        }
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        knowledge_id = sk.teach(
            subject=request.subject,
            content=request.content,
            rationale=request.rationale,
            tags=request.tags
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "message": f"Learned about: {request.subject}"
        }
    except Exception as e:
        logger.error(f"Failed to teach: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ConfigRationaleRequest(BaseModel):
    config_name: str
    description: str
    rationale: str
    tags: Optional[List[str]] = None


@router.post("/knowledge/explain-config")
async def explain_config(request: ConfigRationaleRequest):
    """
    Record WHY something is configured a certain way.
    
    Example:
        POST /api/settings/knowledge/explain-config
        {
            "config_name": "kernel version",
            "description": "Using kernel 6.8.12",
            "rationale": "bcachefs requires kernel 6.8 or earlier"
        }
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        knowledge_id = sk.explain_config(
            config_name=request.config_name,
            description=request.description,
            rationale=request.rationale,
            tags=request.tags
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "message": f"Recorded config rationale for: {request.config_name}"
        }
    except Exception as e:
        logger.error(f"Failed to explain config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RoleRequest(BaseModel):
    component: str
    role: str
    rationale: Optional[str] = None


@router.post("/knowledge/assign-role")
async def assign_role(request: RoleRequest):
    """
    Assign a role/purpose to a component.
    
    Example:
        POST /api/settings/knowledge/assign-role
        {
            "component": "sda",
            "role": "backup disk",
            "rationale": "Dedicated to Borg backup repository"
        }
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        knowledge_id = sk.assign_role(
            component=request.component,
            role=request.role,
            rationale=request.rationale
        )
        
        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "message": f"Assigned role '{request.role}' to {request.component}"
        }
    except Exception as e:
        logger.error(f"Failed to assign role: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/search")
async def search_knowledge(q: str, k: int = 5):
    """Search self-knowledge semantically."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        results = sk.search(q, k=k)
        
        return {
            "query": q,
            "results": [
                {
                    "id": e.id,
                    "type": e.type.value,
                    "subject": e.subject,
                    "content": e.content,
                    "rationale": e.rationale,
                    "source": e.source,
                }
                for e in results
            ],
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Knowledge search failed: {e}")
        return {"query": q, "results": [], "count": 0, "error": str(e)}


@router.get("/knowledge/all")
async def get_all_knowledge():
    """Get all self-knowledge entries."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        entries = []
        for entry in sk._knowledge.values():
            entries.append({
                "id": entry.id,
                "type": entry.type.value,
                "subject": entry.subject,
                "content": entry.content,
                "rationale": entry.rationale,
                "source": entry.source,
                "created_at": entry.created_at,
                "tags": entry.tags,
            })
        
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        logger.error(f"Failed to get knowledge: {e}")
        return {"entries": [], "count": 0, "error": str(e)}


@router.delete("/knowledge/{entry_id:path}")
async def delete_knowledge(entry_id: str):
    """Delete a self-knowledge entry by ID."""
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        
        if entry_id in sk._knowledge:
            del sk._knowledge[entry_id]
            sk._save()
            return {"success": True, "deleted": entry_id}
        else:
            raise HTTPException(status_code=404, detail=f"Knowledge entry not found: {entry_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge/stats")
async def get_knowledge_stats():
    """
    Get memory operation statistics.
    
    Sprint 1: Mem0-style memory tracking.
    Returns counts of ADD/UPDATE/DELETE/NOOP operations.
    """
    try:
        from ...knowledge import get_self_knowledge
        sk = get_self_knowledge()
        return sk.get_memory_stats()
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 23: Approval & Guardrails API
# ─────────────────────────────────────────────────────────────────────────────

from ...approval.engine import ApprovalEngine, ApprovalRequest, ApprovalDecision
from ...autonomy.guardrails import GuardrailEnforcer

_approval_engine: Optional[ApprovalEngine] = None
_guardrail_enforcer: Optional[GuardrailEnforcer] = None

def get_approval_engine() -> ApprovalEngine:
    """Get singleton approval engine."""
    global _approval_engine
    if _approval_engine is None:
        _approval_engine = ApprovalEngine()
    return _approval_engine

def get_guardrail_enforcer() -> GuardrailEnforcer:
    """Get singleton guardrail enforcer."""
    global _guardrail_enforcer
    if _guardrail_enforcer is None:
        _guardrail_enforcer = GuardrailEnforcer()
    return _guardrail_enforcer


def _load_ai_rules() -> list:
    """Load AI rules from config file."""
    try:
        from ...utils.platform import get_config_dir
        import yaml
        
        config_path = get_config_dir() / 'ai_rules.yml'
        if not config_path.exists():
            return []
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        return [r for r in data.get('rules', []) if r.get('enabled', True)]
    except Exception:
        return []


def _check_approval_conflicts(action: str, task: str, affected_resources: list) -> dict:
    """
    Check if an approval request conflicts with any AI rules.
    
    Returns dict with conflict info if found, else None.
    """
    rules = _load_ai_rules()
    if not rules:
        return None
    
    # Build searchable text from approval
    search_text = f"{action} {task} {' '.join(affected_resources or [])}".lower()
    
    for rule in rules:
        rule_text = rule.get('rule', '').lower()
        category = rule.get('category', '')
        
        # Check for kernel-related rules vs kernel updates
        if category == 'kernel' or 'kernel' in rule_text:
            if 'kernel' in search_text and ('update' in search_text or 'upgrade' in search_text):
                return {
                    "has_conflict": True,
                    "conflicting_rule": rule.get('rule'),
                    "rule_category": category,
                    "rule_priority": rule.get('priority', 'medium')
                }
        
        # Check for general keyword matches
        # Look for negative keywords in rules (don't, avoid, never, etc.)
        negative_patterns = ['don\'t', 'dont', 'do not', 'avoid', 'never', 'skip', 'exclude']
        if any(neg in rule_text for neg in negative_patterns):
            # Extract key terms from rule
            keywords = [w for w in rule_text.split() if len(w) > 3 and w not in negative_patterns]
            # If any keyword appears in the approval, flag it
            for kw in keywords[:5]:  # Check first 5 significant words
                if kw in search_text:
                    return {
                        "has_conflict": True,
                        "conflicting_rule": rule.get('rule'),
                        "rule_category": category,
                        "rule_priority": rule.get('priority', 'medium')
                    }
    
    return None


@router.get("/approvals/pending")
async def get_pending_approvals(include_blocked: bool = False):
    """
    Get all pending approval requests.
    
    By default, approvals that conflict with AI Rules are FILTERED OUT.
    Set include_blocked=true to see them with warnings.
    """
    try:
        engine = get_approval_engine()
        pending = engine.get_pending_requests()
        
        results = []
        blocked_count = 0
        
        for req in pending:
            # Check for AI rule conflicts
            conflict = _check_approval_conflicts(
                req.action, 
                req.task, 
                req.affected_resources
            )
            
            # By default, BLOCK approvals that conflict with rules
            if conflict and not include_blocked:
                blocked_count += 1
                logger.info(f"Blocking approval '{req.id}' - conflicts with rule: {conflict.get('conflicting_rule')}")
                continue
            
            item = {
                "id": req.id,
                "task": req.task,
                "action": req.action,
                "reasoning": req.reasoning,
                "confidence": req.confidence,
                "risk_level": req.risk_level,
                "affected_resources": req.affected_resources,
                "requested_at": req.requested_at,
                "simulation_result": req.simulation_result,
            }
            
            if conflict:
                item["rule_conflict"] = conflict
            
            results.append(item)
        
        return {
            "status": "ok",
            "pending": results,
            "count": len(results),
            "blocked_by_rules": blocked_count
        }
    except Exception as e:
        logger.error(f"Failed to get pending approvals: {e}")
        return {"status": "error", "error": str(e), "pending": [], "count": 0}


@router.get("/approvals/history")
async def get_approval_history(limit: int = 50, approved_only: bool = False):
    """Get approval history."""
    try:
        engine = get_approval_engine()
        history = engine.get_approval_history(limit=limit, approved_only=approved_only)
        return {"status": "ok", "history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Failed to get approval history: {e}")
        return {"status": "error", "error": str(e), "history": [], "count": 0}


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    reason: Optional[str] = None
    save_to_memory: bool = True  # Store rejection in AI memory for learning


@router.post("/approvals/{request_id}/decide")
async def decide_approval(request_id: str, decision: ApprovalDecisionRequest):
    """Approve or reject a pending request."""
    try:
        engine = get_approval_engine()
        req = engine.get_request(request_id)
        
        if not req:
            return {"status": "error", "error": f"Request {request_id} not found"}
        
        if req.status != "pending":
            return {"status": "error", "error": f"Request {request_id} is not pending (status: {req.status})"}
        
        # Create decision
        from datetime import datetime, timezone
        approval_decision = ApprovalDecision(
            request_id=request_id,
            approved=decision.approved,
            reason=decision.reason,
            decided_by="dashboard_user",
            decided_at=datetime.now(timezone.utc).isoformat() + 'Z'
        )
        
        # Update request
        req.status = "approved" if decision.approved else "rejected"
        if decision.approved:
            req.approved_at = approval_decision.decided_at
            req.approved_by = "dashboard_user"
        else:
            req.rejected_at = approval_decision.decided_at
            req.rejection_reason = decision.reason
        
        engine._save_request(req)
        engine._save_decision(approval_decision)
        
        # Store ALL decisions in ChromaDB for AI learning
        saved_to_memory = False
        if decision.save_to_memory:
            try:
                from ...index.chroma_index import get_index
                index = get_index()
                
                from datetime import datetime, timezone
                timestamp = datetime.now(timezone.utc).isoformat()
                
                if decision.approved:
                    # Store approval - AI learns what user accepts
                    memory_content = (
                        f"User APPROVED an autonomous action.\n"
                        f"Action: {req.action}\n"
                        f"Task: {req.task}\n"
                        f"AI Reasoning: {req.reasoning}\n"
                        f"Confidence: {req.confidence:.0%}\n"
                        f"Risk Level: {req.risk_level}\n"
                        f"Learn: Similar actions at this confidence/risk level are acceptable to the user."
                    )
                    doc_id = f"approval:{request_id}"
                    doc_type = "user_approval"
                else:
                    # Store rejection - AI learns what to avoid
                    memory_content = (
                        f"User REJECTED an autonomous action.\n"
                        f"Action: {req.action}\n"
                        f"Task: {req.task}\n"
                        f"AI Reasoning: {req.reasoning}\n"
                        f"Confidence: {req.confidence:.0%}\n"
                        f"Risk Level: {req.risk_level}\n"
                        f"User's rejection reason: {decision.reason or 'Not specified'}\n"
                        f"Learn: Avoid similar actions or ask for confirmation. User prefers not to do this."
                    )
                    doc_id = f"rejection:{request_id}"
                    doc_type = "user_rejection"
                
                index.upsert_memory(
                    collection="self_knowledge_all",
                    doc_id=doc_id,
                    text=memory_content,
                    metadata={
                        "type": doc_type,
                        "request_id": request_id,
                        "action": req.action,
                        "task": req.task,
                        "confidence": req.confidence,
                        "risk_level": req.risk_level,
                        "approved": decision.approved,
                        "reason": decision.reason,
                        "timestamp": timestamp
                    }
                )
                logger.info(f"Saved {doc_type} to memory: {request_id}")
                saved_to_memory = True
            except Exception as mem_err:
                logger.warning(f"Failed to save decision to memory: {mem_err}")
        
        return {
            "status": "ok",
            "request_id": request_id,
            "decision": "approved" if decision.approved else "rejected",
            "reason": decision.reason,
            "saved_to_memory": saved_to_memory
        }
    except Exception as e:
        logger.error(f"Failed to process approval decision: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Policy Configuration API
# ─────────────────────────────────────────────────────────────────────────────

def _get_policy_path() -> Path:
    """Get the policy.yml path."""
    # Check user config first, then system
    from ...utils.platform import get_config_dir
    user_path = get_config_dir() / 'policy.yml'
    if user_path.exists():
        return user_path
    # Fall back to project config
    return Path("config/policy.yml")


@router.get("/policy")
async def get_policy():
    """Get current policy configuration."""
    try:
        import yaml
        path = _get_policy_path()
        
        if not path.exists():
            return {
                "status": "ok",
                "policy": {"default_allow": True, "tools": {}},
                "path": str(path),
                "exists": False
            }
        
        with open(path, 'r') as f:
            policy = yaml.safe_load(f) or {}
        
        return {
            "status": "ok",
            "policy": policy,
            "path": str(path),
            "exists": True
        }
    except Exception as e:
        logger.error(f"Failed to get policy: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/policy")
async def update_policy(request: Request):
    """Update policy configuration."""
    try:
        import yaml
        data = await request.json()
        
        policy = data.get("policy", {})
        path = _get_policy_path()
        
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with comments
        content = """# Halbert Policy Configuration
# Controls whether side-effecting tools may apply changes.

# If true, tools are allowed by default unless overridden below.
# If false, tools are denied by default unless explicitly allowed.
default_allow: {default_allow}

# Per-tool overrides
tools:
""".format(default_allow=str(policy.get('default_allow', True)).lower())
        
        tools = policy.get('tools', {})
        for tool_name, tool_config in tools.items():
            if isinstance(tool_config, dict):
                content += f"  {tool_name}:\n"
                for key, value in tool_config.items():
                    content += f"    {key}: {str(value).lower() if isinstance(value, bool) else value}\n"
            else:
                content += f"  {tool_name}: {tool_config}\n"
        
        with open(path, 'w') as f:
            f.write(content)
        
        logger.info(f"Updated policy at {path}")
        return {"status": "ok", "path": str(path)}
    except Exception as e:
        logger.error(f"Failed to update policy: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/policy/tool")
async def set_tool_policy(request: Request):
    """Set policy for a specific tool."""
    try:
        import yaml
        data = await request.json()
        
        tool_name = data.get("tool")
        allow = data.get("allow", True)
        require_approval = data.get("require_approval", False)
        
        if not tool_name:
            return {"status": "error", "error": "Tool name required"}
        
        path = _get_policy_path()
        
        # Load existing policy
        if path.exists():
            with open(path, 'r') as f:
                policy = yaml.safe_load(f) or {}
        else:
            policy = {"default_allow": True, "tools": {}}
        
        # Update tool config
        if "tools" not in policy:
            policy["tools"] = {}
        
        policy["tools"][tool_name] = {
            "allow": allow,
            "require_approval": require_approval
        }
        
        # Save back
        with open(path, 'w') as f:
            yaml.dump(policy, f, default_flow_style=False)
        
        return {"status": "ok", "tool": tool_name, "config": policy["tools"][tool_name]}
    except Exception as e:
        logger.error(f"Failed to set tool policy: {e}")
        return {"status": "error", "error": str(e)}


@router.delete("/policy/tool/{tool_name}")
async def delete_tool_policy(tool_name: str):
    """Remove policy override for a specific tool."""
    try:
        import yaml
        path = _get_policy_path()
        
        if not path.exists():
            return {"status": "error", "error": "Policy file not found"}
        
        with open(path, 'r') as f:
            policy = yaml.safe_load(f) or {}
        
        if "tools" in policy and tool_name in policy["tools"]:
            del policy["tools"][tool_name]
            
            with open(path, 'w') as f:
                yaml.dump(policy, f, default_flow_style=False)
            
            return {"status": "ok", "tool": tool_name, "deleted": True}
        
        return {"status": "ok", "tool": tool_name, "deleted": False}
    except Exception as e:
        logger.error(f"Failed to delete tool policy: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/guardrails/status")
async def get_guardrails_status():
    """Get current guardrails status."""
    try:
        enforcer = get_guardrail_enforcer()
        return {
            "status": "ok",
            "safe_mode_active": enforcer.is_safe_mode_active(),
            "config": enforcer.config
        }
    except Exception as e:
        logger.error(f"Failed to get guardrails status: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/guardrails/safe-mode/enter")
async def enter_safe_mode(reason: str = "Manual activation"):
    """Enter safe mode (pause autonomous operations)."""
    try:
        enforcer = get_guardrail_enforcer()
        enforcer.enter_safe_mode(reason)
        return {"status": "ok", "safe_mode_active": True, "reason": reason}
    except Exception as e:
        logger.error(f"Failed to enter safe mode: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/guardrails/safe-mode/exit")
async def exit_safe_mode():
    """Exit safe mode (resume autonomous operations)."""
    try:
        enforcer = get_guardrail_enforcer()
        enforcer.exit_safe_mode("dashboard_user")
        return {"status": "ok", "safe_mode_active": False}
    except Exception as e:
        logger.error(f"Failed to exit safe mode: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Anomaly Detection API
# ─────────────────────────────────────────────────────────────────────────────

# Singleton anomaly detector
_anomaly_detector = None

def get_anomaly_detector():
    """Get or create singleton anomaly detector."""
    global _anomaly_detector
    if _anomaly_detector is None:
        from ...autonomy import AnomalyDetector
        import yaml
        try:
            with open("config/autonomy.yml", "r") as f:
                config = yaml.safe_load(f) or {}
            anomaly_config = config.get("anomalies", {
                "cpu_spike_threshold": 90,
                "memory_leak_mb": 500,
                "repeated_failures": 3,
                "error_rate_threshold": 0.5
            })
        except Exception:
            anomaly_config = {
                "cpu_spike_threshold": 90,
                "memory_leak_mb": 500,
                "repeated_failures": 3,
                "error_rate_threshold": 0.5
            }
        _anomaly_detector = AnomalyDetector(anomaly_config)
    return _anomaly_detector


@router.get("/anomaly/status")
async def get_anomaly_status():
    """Get anomaly detection status and recent anomalies."""
    try:
        detector = get_anomaly_detector()
        summary = detector.get_summary()
        recent = detector.get_recent_anomalies(hours=24)
        
        return {
            "status": "ok",
            "summary": summary,
            "recent_anomalies": [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "description": a.description,
                    "metrics": a.metrics
                }
                for a in recent
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get anomaly status: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/anomaly/check")
async def run_anomaly_check():
    """Run anomaly detection checks now."""
    try:
        detector = get_anomaly_detector()
        
        results = {
            "cpu_spike": detector.check_cpu_spike(),
            "error_rate_high": detector.check_error_rate()
        }
        
        # Get updated summary
        summary = detector.get_summary()
        
        return {
            "status": "ok",
            "checks": results,
            "anomalies_detected": any(results.values()),
            "summary": summary
        }
    except Exception as e:
        logger.error(f"Failed to run anomaly check: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Recovery Playbooks API
# ─────────────────────────────────────────────────────────────────────────────

# Singleton recovery executor
_recovery_executor = None

def get_recovery_executor():
    """Get or create singleton recovery executor."""
    global _recovery_executor
    if _recovery_executor is None:
        from ...autonomy import RecoveryExecutor
        import yaml
        try:
            with open("config/autonomy.yml", "r") as f:
                config = yaml.safe_load(f) or {}
            recovery_config = config.get("recovery", {
                "rollback": {"enabled": True, "max_rollback_depth": 5},
                "restart_service": {"enabled": True, "max_restart_attempts": 3},
                "alert_user": {"enabled": True, "throttle_minutes": 30}
            })
        except Exception:
            recovery_config = {
                "rollback": {"enabled": True, "max_rollback_depth": 5},
                "restart_service": {"enabled": True, "max_restart_attempts": 3},
                "alert_user": {"enabled": True, "throttle_minutes": 30}
            }
        _recovery_executor = RecoveryExecutor(recovery_config)
    return _recovery_executor


@router.get("/recovery/status")
async def get_recovery_status():
    """Get recovery playbook status and history."""
    try:
        executor = get_recovery_executor()
        summary = executor.get_summary()
        
        return {
            "status": "ok",
            "summary": summary,
            "config": executor.config
        }
    except Exception as e:
        logger.error(f"Failed to get recovery status: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/recovery/rollback")
async def execute_rollback(request: Request):
    """Execute rollback for a config file."""
    try:
        data = await request.json()
        file_path = data.get("file_path")
        
        if not file_path:
            return {"status": "error", "error": "file_path required"}
        
        executor = get_recovery_executor()
        result = executor.execute_rollback(file_path)
        
        return {
            "status": "ok" if result.success else "error",
            "action": result.action.value,
            "success": result.success,
            "message": result.message,
            "details": result.details
        }
    except Exception as e:
        logger.error(f"Failed to execute rollback: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/recovery/restart-service")
async def execute_restart_service(request: Request):
    """Execute service restart recovery."""
    try:
        data = await request.json()
        service_name = data.get("service")
        
        if not service_name:
            return {"status": "error", "error": "service required"}
        
        executor = get_recovery_executor()
        result = executor.execute_restart_service(service_name)
        
        return {
            "status": "ok" if result.success else "error",
            "action": result.action.value,
            "success": result.success,
            "message": result.message,
            "details": result.details
        }
    except Exception as e:
        logger.error(f"Failed to execute service restart: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/recovery/alert")
async def execute_alert(request: Request):
    """Send recovery alert to user."""
    try:
        data = await request.json()
        message = data.get("message", "Recovery alert")
        severity = data.get("severity", "warning")
        
        executor = get_recovery_executor()
        result = executor.execute_alert_user(message, severity)
        
        return {
            "status": "ok" if result.success else "error",
            "action": result.action.value,
            "success": result.success,
            "message": result.message
        }
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Dry-Run Simulation API
# ─────────────────────────────────────────────────────────────────────────────

# Singleton simulator
_dry_run_simulator = None

def get_dry_run_simulator():
    """Get or create singleton dry-run simulator."""
    global _dry_run_simulator
    if _dry_run_simulator is None:
        from ...approval.simulator import DryRunSimulator
        _dry_run_simulator = DryRunSimulator()
    return _dry_run_simulator


@router.post("/simulate/file-write")
async def simulate_file_write(request: Request):
    """Simulate a file write operation (dry-run preview)."""
    try:
        data = await request.json()
        path = data.get("path")
        new_content = data.get("content", "")
        current_content = data.get("current_content")
        
        if not path:
            return {"status": "error", "error": "path required"}
        
        # Try to read current content if not provided
        if current_content is None:
            from pathlib import Path
            file_path = Path(path)
            if file_path.exists():
                try:
                    current_content = file_path.read_text()
                except Exception:
                    current_content = None
        
        simulator = get_dry_run_simulator()
        result = simulator.simulate_file_write(path, new_content, current_content)
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "changes": result.changes,
                "affected_files": result.affected_files,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible,
                "rollback_strategy": result.rollback_strategy
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate file write: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/simulate/command")
async def simulate_command(request: Request):
    """Simulate a command execution (dry-run preview)."""
    try:
        data = await request.json()
        command = data.get("command")
        dry_run_flag = data.get("dry_run_flag")
        
        if not command:
            return {"status": "error", "error": "command required"}
        
        simulator = get_dry_run_simulator()
        result = simulator.simulate_command(command, dry_run_flag)
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "changes": result.changes,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate command: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/simulate/service-restart")
async def simulate_service_restart(request: Request):
    """Simulate a service restart (dry-run preview)."""
    try:
        data = await request.json()
        service = data.get("service")
        
        if not service:
            return {"status": "error", "error": "service required"}
        
        simulator = get_dry_run_simulator()
        result = simulator.simulate_service_restart(service)
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "changes": result.changes,
                "affected_services": result.affected_services,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible,
                "rollback_strategy": result.rollback_strategy
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate service restart: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/simulate/tool")
async def simulate_tool_call(request: Request):
    """
    Simulate any tool call based on tool name and arguments.
    Routes to appropriate simulation based on tool type.
    """
    try:
        data = await request.json()
        tool_name = data.get("tool")
        tool_args = data.get("args", {})
        
        if not tool_name:
            return {"status": "error", "error": "tool required"}
        
        simulator = get_dry_run_simulator()
        
        # Route to appropriate simulation based on tool
        if tool_name == "write_config":
            path = tool_args.get("path", "")
            content = tool_args.get("content", "")
            result = simulator.simulate_file_write(path, content)
        elif tool_name == "run_command":
            command = tool_args.get("command", "")
            result = simulator.simulate_command(command)
        elif tool_name == "restart_service":
            service = tool_args.get("service", "")
            result = simulator.simulate_service_restart(service)
        elif tool_name == "update_packages":
            packages = tool_args.get("packages", [])
            pm = tool_args.get("package_manager", "apt")
            result = simulator.simulate_package_update(packages, pm)
        elif tool_name == "fan_control":
            current = tool_args.get("current_rpm", 2000)
            target = tool_args.get("target_rpm", 3000)
            hwmon = tool_args.get("hwmon_path", "/sys/class/hwmon/hwmon0/pwm1")
            result = simulator.simulate_fan_throttle(current, target, hwmon)
        else:
            # Generic simulation for unknown tools
            return {
                "status": "ok",
                "simulation": {
                    "success": True,
                    "action": f"Execute tool: {tool_name}",
                    "changes": [{"type": "tool_call", "tool": tool_name, "args": tool_args}],
                    "warnings": [f"No specific simulation for '{tool_name}' - showing args only"],
                    "commands_to_run": [f"{tool_name}({tool_args})"],
                    "estimated_duration_s": 1.0,
                    "reversible": False
                }
            }
        
        return {
            "status": "ok",
            "simulation": {
                "success": result.success,
                "action": result.action,
                "before": result.before,
                "after": result.after,
                "changes": result.changes,
                "affected_files": result.affected_files,
                "affected_services": result.affected_services,
                "warnings": result.warnings,
                "commands_to_run": result.commands_to_run,
                "estimated_duration_s": result.estimated_duration_s,
                "reversible": result.reversible,
                "rollback_strategy": result.rollback_strategy
            }
        }
    except Exception as e:
        logger.error(f"Failed to simulate tool call: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 23: Scheduler API
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and job list."""
    try:
        from ..app import _scheduler_executor
        
        if _scheduler_executor is None:
            return {
                "status": "ok",
                "scheduler": {
                    "running": False,
                    "reason": "Scheduler not initialized"
                }
            }
        
        status = _scheduler_executor.get_status()
        jobs = _scheduler_executor.get_scheduled_jobs()
        
        return {
            "status": "ok",
            "scheduler": status,
            "jobs": jobs
        }
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/scheduler/jobs")
async def list_scheduler_jobs():
    """List all scheduled jobs."""
    try:
        from ..app import _scheduler_executor
        
        if _scheduler_executor is None:
            return {"status": "ok", "jobs": []}
        
        jobs = _scheduler_executor.get_scheduled_jobs()
        return {"status": "ok", "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return {"status": "error", "error": str(e), "jobs": []}


@router.post("/scheduler/jobs/{job_id}/cancel")
async def cancel_scheduler_job(job_id: str):
    """Cancel a scheduled job."""
    try:
        from ..app import _scheduler_executor
        
        if _scheduler_executor is None:
            return {"status": "error", "error": "Scheduler not running"}
        
        success = _scheduler_executor.cancel_job(job_id)
        return {"status": "ok" if success else "error", "cancelled": success}
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        return {"status": "error", "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Testing Endpoints (Development Only)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/approvals/test/create")
async def create_test_approval(
    task: str = "Test Action",
    action: str = "This is a test approval request for development",
    risk_level: str = "medium"
):
    """
    Create a test approval request for development/testing.
    
    This helps verify the approval flow works end-to-end.
    """
    try:
        import uuid
        from datetime import datetime, timezone
        from ...approval.engine import ApprovalRequest
        
        engine = get_approval_engine()
        
        request = ApprovalRequest(
            id=f"test_{uuid.uuid4().hex[:8]}",
            task=task,
            action=action,
            reasoning="Created via test endpoint for development purposes",
            confidence=0.7,  # Below auto-execute threshold
            risk_level=risk_level,
            system_state={"source": "test_endpoint"},
            affected_resources=["test"],
            requested_at=datetime.now(timezone.utc).isoformat() + 'Z',
            requested_by="test_endpoint"
        )
        
        engine.queue_request(request)
        
        return {
            "status": "ok",
            "message": "Test approval created",
            "request_id": request.id,
            "note": "Check the Approvals page to see it"
        }
    except Exception as e:
        logger.error(f"Failed to create test approval: {e}")
        return {"status": "error", "error": str(e)}
