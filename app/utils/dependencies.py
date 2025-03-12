from typing import Optional
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session
from app.services.auth_service import AuthService
from app.utils.auth import verify_token
from app.models.user import User
from app.schemas.auth import TokenData
import uuid

# Security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """Get current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = verify_token(credentials.credentials)
        if payload is None:
            raise credentials_exception
        
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
        token_data = TokenData(user_id=uuid.UUID(user_id))
    except (ValueError, TypeError):
        raise credentials_exception
    
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id=token_data.user_id)
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_current_verified_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Get current verified user"""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified"
        )
    return current_user


async def get_user_from_api_key(
    api_key: str,
    db: AsyncSession = Depends(get_async_session)
) -> Optional[User]:
    """Get user from API key"""
    auth_service = AuthService(db)
    return await auth_service.get_user_by_api_key(api_key)


async def validate_api_key(
    api_key: str = None,
    db: AsyncSession = Depends(get_async_session)
) -> User:
    """Validate API key and return user"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    user = await get_user_from_api_key(api_key, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security, auto_error=False),
    db: AsyncSession = Depends(get_async_session)
) -> Optional[User]:
    """Get user if authenticated, otherwise None (for optional authentication)"""
    if credentials is None:
        return None
    
    try:
        payload = verify_token(credentials.credentials)
        if payload is None:
            return None
        
        user_id = payload.get("sub")
        if user_id is None:
            return None
        
        auth_service = AuthService(db)
        return auth_service.get_user_by_id(user_id=uuid.UUID(user_id))
    except Exception:
        return None