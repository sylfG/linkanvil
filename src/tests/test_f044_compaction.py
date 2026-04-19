import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.ui.chatbot import async_update_session_context, async_get_session_context
from src.data.db import DatabaseManager

@pytest.mark.asyncio
async def test_f044_compaction_flow():
    tenant_id = "tenant_f044"
    session_id = "session_f044"
    
    # Prepare
    await async_update_session_context(tenant_id, session_id, "Old Compressed Context")
    
    # Verify retrieval
    ctx = await async_get_session_context(tenant_id, session_id)
    assert ctx == "Old Compressed Context"
    
    # Verify update
    await async_update_session_context(tenant_id, session_id, "New Compressed Context")
    ctx = await async_get_session_context(tenant_id, session_id)
    assert ctx == "New Compressed Context"
    
    # Cleanup
    db = DatabaseManager()
    await db.connect()
    async with db.pool.acquire() as conn:
        import hashlib, uuid
        m = hashlib.md5()
        m.update(session_id.encode('utf-8'))
        s_uuid = uuid.UUID(m.hexdigest())
        await conn.execute("DELETE FROM sesiones_chat WHERE id = $1 AND tenant_id = $2", s_uuid, tenant_id)
    await db.close()
