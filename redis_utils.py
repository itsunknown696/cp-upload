import redis
import json
from typing import Optional, Dict, Any

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, db=0)

def is_bot_busy() -> bool:
    """Check if bot is currently processing any request"""
    return bool(r.get('bot:busy'))

def set_bot_busy(status: bool = True):
    """Set bot busy status"""
    r.set('bot:busy', int(status))

def get_user_state(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user conversation state"""
    data = r.get(f'user:{user_id}:state')
    return json.loads(data) if data else None

def set_user_state(user_id: int, state: Dict[str, Any]):
    """Set user conversation state"""
    r.set(f'user:{user_id}:state', json.dumps(state))

def clear_user_state(user_id: int):
    """Clear user conversation state"""
    r.delete(f'user:{user_id}:state')
