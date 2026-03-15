"""
backend/auth.py
Supabase JWT verification — supports both HS256 (legacy) and ES256 (new ECC keys).
"""

import os
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL        = os.getenv("SUPABASE_URL")         # e.g. https://xxxx.supabase.co
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # legacy HS256 secret

security = HTTPBearer()

# Cache the JWKS (public keys for ES256 verification)
_jwks_cache = None

def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        response = httpx.get(url, timeout=10)
        _jwks_cache = response.json()
    return _jwks_cache


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = credentials.credentials

    # Peek at the header to find the algorithm
    try:
        header = jwt.get_unverified_header(token)
        alg    = header.get("alg", "HS256")
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Bad token header: {e}")

    try:
        if alg == "HS256":
            # Legacy secret verification
            if not SUPABASE_JWT_SECRET:
                raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET not set")
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
        elif alg == "ES256":
            # New ECC key verification via JWKS
            jwks    = get_jwks()
            payload = jwt.decode(
                token,
                jwks,
                algorithms=["ES256"],
                options={"verify_aud": False}
            )
        else:
            raise HTTPException(status_code=401, detail=f"Unsupported algorithm: {alg}")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token has no user ID")
        return user_id

    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")