# ARCHITECTURAL SHIFT: Signaling Efficiency
# Instead of iterating 2000 users in a loop (O(N)), we update the room metadata once (O(1)).
# All clients listen for the 'room_metadata_changed' event and update their local PTT permissions.

@rooms_bp.route("/api/rooms/<room_id>/mode", methods=["POST"])
@mod_required
def toggle_mode(room_id):
    data = request.get_json(force=True)
    new_mode = data.get("mode", "")
    
    # 1. Update DB (Source of Truth)
    db.rooms.update_one({"_id": room_id}, {"$set": {"mode": new_mode}})
    
    # 2. Update LiveKit Room Metadata (Broadcast Signal)
    # This triggers a single packet to all 2000 users.
    lk.update_room_metadata(room_id, json.dumps({"mode": new_mode}))
    
    return jsonify({"mode": new_mode})
