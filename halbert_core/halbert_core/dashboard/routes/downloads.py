"""
Dataset Download API Routes

Endpoints for managing dataset downloads from external sources.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class DownloadRequest(BaseModel):
    """Request to start a download."""
    dataset_id: str


@router.get("/datasets")
async def list_datasets():
    """
    List all available datasets and their download status.
    
    Returns datasets from the manifest with current status.
    """
    from ...downloads import get_dataset_manager
    
    manager = get_dataset_manager()
    datasets = manager.get_all_datasets()
    
    # Group by category
    by_category = {}
    for ds in datasets:
        cat = ds.get('category', 'other')
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(ds)
    
    return {
        'datasets': datasets,
        'by_category': by_category,
        'total_count': len(datasets),
        'downloaded_count': sum(1 for ds in datasets if ds['status'] == 'completed'),
    }


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    """Get info for a specific dataset."""
    from ...downloads import get_dataset_manager
    
    manager = get_dataset_manager()
    info = manager.get_dataset(dataset_id)
    
    if not info:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
    
    return info


@router.get("/datasets/{dataset_id}/status")
async def get_download_status(dataset_id: str):
    """Get download status for a dataset."""
    from ...downloads import get_dataset_manager
    
    manager = get_dataset_manager()
    status = manager.get_download_status(dataset_id)
    
    if not status:
        # Return not_downloaded status
        info = manager.get_dataset(dataset_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")
        return {
            'dataset_id': dataset_id,
            'status': 'not_downloaded',
            'progress': 0,
            'downloaded_bytes': 0,
            'total_bytes': info.get('size_bytes', 0),
        }
    
    return status


@router.post("/datasets/{dataset_id}/download")
async def start_download(dataset_id: str):
    """
    Start downloading a dataset.
    
    Downloads from Hugging Face Hub in background.
    Poll /status endpoint for progress.
    """
    from ...downloads import get_dataset_manager
    
    manager = get_dataset_manager()
    result = manager.start_download(dataset_id)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.post("/datasets/{dataset_id}/cancel")
async def cancel_download(dataset_id: str):
    """Cancel an active download."""
    from ...downloads import get_dataset_manager
    
    manager = get_dataset_manager()
    result = manager.cancel_download(dataset_id)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """Delete a downloaded dataset to free disk space."""
    from ...downloads import get_dataset_manager
    
    manager = get_dataset_manager()
    result = manager.delete_dataset(dataset_id)
    
    if 'error' in result:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result
