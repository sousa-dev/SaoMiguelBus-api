from __future__ import annotations

def error(code: str, message: str) -> dict:
    return {'error': {'code': code, 'message': message}}