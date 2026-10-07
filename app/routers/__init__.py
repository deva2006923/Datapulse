from typing import Callable, Any
from fastapi import APIRouter

class TrailingSlashRouter(APIRouter):
    """
    An APIRouter that automatically registers both trailing-slash and 
    non-trailing-slash variations of every route without performing 307 redirects.
    This guarantees Authorization headers and HTTP methods are never dropped.
    """
    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().add_api_route(path, endpoint, **kwargs)
        
        # Calculate the alternate path (with or without trailing slash)
        if path.endswith("/"):
            alt_path = path.rstrip("/")
        else:
            alt_path = path + "/"
            
        if alt_path and alt_path != path:
            alt_kwargs = dict(kwargs)
            # Prevent duplicate entries in Swagger UI / OpenAPI docs
            alt_kwargs["include_in_schema"] = False
            super().add_api_route(alt_path, endpoint, **alt_kwargs)
