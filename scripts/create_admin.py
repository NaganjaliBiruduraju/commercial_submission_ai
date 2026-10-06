"""
Create an admin user via direct database insertion.
Run this once to create your first admin account.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.user import User, Role
from app.core.constants import UserRole


async def create_admin_user():
    """Create admin user directly in the database."""
    settings = get_settings()
    
    print(f"Connecting to database: {settings.database_url[:40]}...")
    
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as db:
        # Get admin role
        result = await db.execute(select(Role).where(Role.name == UserRole.ADMIN.value))
        admin_role = result.scalar_one_or_none()
        
        if not admin_role:
            print("❌ Admin role not found. Run database migrations first.")
            return
        
        # Check if admin already exists
        admin_email = "admin@example.com"
        result = await db.execute(select(User).where(User.email == admin_email))
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"✅ Admin user already exists: {admin_email}")
            print(f"   Password: admin123 (or what you set in .env)")
            return
        
        # Create admin user
        admin_user = User(
            email=admin_email,
            hashed_password=hash_password("admin123"),
            full_name="System Administrator",
            role_id=admin_role.id,
            is_active=True,
        )
        db.add(admin_user)
        await db.commit()
        
        print("✅ Admin user created successfully!")
        print(f"   Email: {admin_email}")
        print(f"   Password: admin123")
        print("")
        print("⚠️  IMPORTANT: Change this password immediately after first login!")
        print("")
        print("Login at: http://localhost:8000/docs")
        print("  1. Click 'Authorize' button (top right)")
        print("  2. Or use POST /api/v1/auth/login endpoint")


if __name__ == "__main__":
    asyncio.run(create_admin_user())
