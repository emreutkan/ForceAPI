import base64
import json
import urllib.request
from functools import lru_cache

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


@lru_cache(maxsize=10)
def _fetch_jwks(supabase_url: str, anon_key: str) -> tuple:
    """Fetch and cache JWKS keys from Supabase. Returns a tuple (hashable for lru_cache)."""
    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    req = urllib.request.Request(jwks_url, headers={'apikey': anon_key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return tuple(json.dumps(k) for k in data.get('keys', []))


def _get_public_key_for_kid(kid: str):
    """Return the PyJWT-compatible public key for the given kid."""
    supabase_url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
    anon_key = getattr(settings, 'SUPABASE_ANON_KEY', '')

    if not supabase_url or not anon_key:
        return None

    try:
        raw_keys = _fetch_jwks(supabase_url, anon_key)
    except Exception:
        return None

    from jwt.algorithms import ECAlgorithm, RSAAlgorithm

    for raw_key in raw_keys:
        key_data = json.loads(raw_key)
        if key_data.get('kid') != kid:
            continue
        alg = key_data.get('alg', '')
        if alg.startswith('ES'):
            return ECAlgorithm.from_jwk(raw_key)
        elif alg.startswith('RS'):
            return RSAAlgorithm.from_jwk(raw_key)

    return None


class SupabaseJWTAuthentication(BaseAuthentication):
    """
    Verifies a Supabase-issued JWT sent as 'Authorization: Bearer <token>'.
    Supports HS256 (legacy) and ES256/RS256 (modern asymmetric signing via JWKS).
    On success, returns the matching (or newly created) Django user.
    """

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ', 1)[1].strip()
        if not token:
            return None

        payload = self._decode(token)
        user = self._get_or_create_user(payload)
        return (user, token)

    def _decode(self, token):
        # Peek at the JWT header to determine algorithm without verifying
        try:
            header_part = token.split('.')[0]
            padding = 4 - len(header_part) % 4
            if padding != 4:
                header_part += '=' * padding
            header = json.loads(base64.urlsafe_b64decode(header_part))
        except Exception as e:
            raise AuthenticationFailed(f'Invalid token format: {e}')

        alg = header.get('alg', 'HS256')
        kid = header.get('kid')

        try:
            if alg == 'HS256':
                secret = getattr(settings, 'SUPABASE_JWT_SECRET', None)
                if not secret:
                    raise AuthenticationFailed('SUPABASE_JWT_SECRET is not configured')
                payload = jwt.decode(
                    token, secret, algorithms=['HS256'], audience='authenticated'
                )
            elif alg in ('ES256', 'RS256'):
                public_key = _get_public_key_for_kid(kid)
                if not public_key:
                    raise AuthenticationFailed(
                        f'SUPABASE_URL/SUPABASE_ANON_KEY not configured or key not found for kid: {kid}'
                    )
                payload = jwt.decode(
                    token, public_key, algorithms=[alg], audience='authenticated'
                )
            else:
                raise AuthenticationFailed(f'Unsupported JWT algorithm: {alg}')
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f'Invalid token: {e}')
        except AuthenticationFailed:
            raise
        except Exception as e:
            raise AuthenticationFailed(f'Token verification error: {e}')

        return payload

    def _get_or_create_user(self, payload):
        supabase_uid = payload.get('sub')
        email = (payload.get('email') or '').strip()

        if not supabase_uid:
            raise AuthenticationFailed('Token missing sub claim')

        # Prefer lookup by Supabase UID (linked account)
        user = User.objects.filter(supabase_uid=supabase_uid).first()
        if user:
            if email and user.email != email:
                user.email = email
                user.save(update_fields=['email'])
            return user

        # New Supabase user: create or link existing Django user by email
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                user.supabase_uid = supabase_uid
                user.is_verified = True
                user.save(update_fields=['supabase_uid', 'is_verified'])
                return user

        # No existing user: create one
        user = User.objects.create(
            email=email or f"{supabase_uid}@supabase.user",
            supabase_uid=supabase_uid,
            is_verified=True,
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user
