import asyncio
from livekit import api
from .config import LIVEKIT_INTERNAL_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET


def lk_run(coro):
    """Run an async LiveKit SDK coroutine synchronously. Safe from gevent greenlets."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


async def _list_participants(room_name: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        resp = await lk.room.list_participants(api.ListParticipantsRequest(room=room_name))
        return list(resp.participants)


async def _update_participant(room_name: str, identity: str, can_publish: bool, can_subscribe: bool = True):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        await lk.room.update_participant(api.UpdateParticipantRequest(
            room=room_name,
            identity=identity,
            permission=api.ParticipantPermission(
                can_publish=can_publish,
                can_subscribe=can_subscribe,
                can_publish_data=can_publish,
            ),
        ))


async def _update_room_metadata(room_name: str, metadata: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        await lk.room.update_room_metadata(api.UpdateRoomMetadataRequest(
            room=room_name,
            metadata=metadata,
        ))


async def _list_rooms():
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        resp = await lk.room.list_rooms(api.ListRoomsRequest())
        return {r.name: r.num_participants for r in resp.rooms}


async def _start_egress(room_name: str, filepath: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        egress = await lk.egress.start_room_composite_egress(
            api.RoomCompositeEgressRequest(
                room_name=room_name,
                file_outputs=[api.EncodedFileOutput(filepath=filepath)],
            )
        )
        return egress.egress_id


async def _stop_egress(egress_id: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        await lk.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))


def list_participants(room_name: str):
    return lk_run(_list_participants(room_name))


def update_participant(room_name: str, identity: str, can_publish: bool, can_subscribe: bool = True):
    lk_run(_update_participant(room_name, identity, can_publish, can_subscribe))


def update_room_metadata(room_name: str, metadata: str):
    lk_run(_update_room_metadata(room_name, metadata))


def list_rooms_participants() -> dict:
    try:
        return lk_run(_list_rooms())
    except Exception:
        return {}


def start_egress(room_name: str, filepath: str) -> str:
    return lk_run(_start_egress(room_name, filepath))


def stop_egress(egress_id: str):
    lk_run(_stop_egress(egress_id))
