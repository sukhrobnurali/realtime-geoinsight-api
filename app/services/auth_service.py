from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, User as UserSchema
from app.utils.auth import get_password_hash, verify_password, generate_api_key
import uuid


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user"""
        # Check if user already exists
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Hash password and create user
        hashed_password = get_password_hash(user_data.password)
        api_key = generate_api_key()
        
        db_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            api_key=api_key,
            is_active=user_data.is_active,
            is_verified=user_data.is_verified
        )
        
        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        
        return db_user

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_api_key(self, api_key: str) -> Optional[User]:
        """Get user by API key"""
        result = await self.db.execute(
            select(User).where(User.api_key == api_key, User.is_active == True)
        )
        return result.scalar_one_or_none()

    async def update_user_password(self, user_id: uuid.UUID, new_password: str) -> bool:
        """Update user password"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.hashed_password = get_password_hash(new_password)
        await self.db.commit()
        return True

    async def regenerate_api_key(self, user_id: uuid.UUID) -> Optional[str]:
        """Regenerate API key for user"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        new_api_key = generate_api_key()
        user.api_key = new_api_key
        await self.db.commit()
        return new_api_key

    async def deactivate_user(self, user_id: uuid.UUID) -> bool:
        """Deactivate user account"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_active = False
        await self.db.commit()
        return True

    async def verify_user_email(self, user_id: uuid.UUID) -> bool:
        """Mark user email as verified"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        user.is_verified = True
        await self.db.commit()
        return True