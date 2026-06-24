import asyncio
import threading
from livekit import api
from .config import LIVEKIT_INTERNAL_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

# Persistent background loop thread
_loop = None
_thread = None

def _start_background_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

def lk_run(coro):
    """Run an async LiveKit SDK coroutine in the persistent background loop."""
    global _loop, _thread
    if _loop is None or not _thread.is_alive():
        _thread = threading.Thread(target=_start_background_loop, daemon=True)
        _thread.start()
        # Wait for loop to be ready
        import time
        while _loop is None: time.sleep(0.01)

    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result()


async def _list_participants(room_name: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        resp = await lk.room.list_participants(api.ListParticipantsRequest(room=room_name))
        return list(resp.participants)


async def _update_participant(room_name: str, identity: str, can_publish: bool,
                              can_subscribe: bool = True, can_publish_data: bool = True):
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
                # Always allow DATA (hand-raise, chat) even when audio is muted —
                # tying this to can_publish was stripping hand-raise on broadcast mute.
                can_publish_data=can_publish_data,
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


async def _get_room_metadata(room_name: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        rooms = await lk.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
        if rooms.rooms:
            return rooms.rooms[0].metadata
        return None


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


async def _remove_participant(room_name: str, identity: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        await lk.room.remove_participant(api.RemoveParticipantRequest(
            room=room_name,
            identity=identity,
        ))


async def _delete_room(room_name: str):
    async with api.LiveKitAPI(
        url=LIVEKIT_INTERNAL_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lk:
        await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))


def list_participants(room_name: str):
    return lk_run(_list_participants(room_name))


def update_participant(room_name: str, identity: str, can_publish: bool,
                       can_subscribe: bool = True, can_publish_data: bool = True):
    lk_run(_update_participant(room_name, identity, can_publish, can_subscribe, can_publish_data))


def update_room_metadata(room_name: str, metadata: str):
    lk_run(_update_room_metadata(room_name, metadata))


def get_room_metadata(room_name: str) -> str:
    return lk_run(_get_room_metadata(room_name))


def list_rooms_participants() -> dict:
    try:
        return lk_run(_list_rooms())
    except Exception:
        return {}


def start_egress(room_name: str, filepath: str) -> str:
    return lk_run(_start_egress(room_name, filepath))


def stop_egress(egress_id: str):
    lk_run(_stop_egress(egress_id))


def remove_participant(room_name: str, identity: str):
    lk_run(_remove_participant(room_name, identity))


def delete_room(room_name: str):
    lk_run(_delete_room(room_name))
