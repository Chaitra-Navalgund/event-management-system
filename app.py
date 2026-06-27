from flask import Flask, jsonify, render_template, request
from db import db

app = Flask(__name__)


def get_cursor():
    if not db.is_connected():
        db.reconnect()
    return db.cursor(dictionary=True)


def serialize_event(row):
    return {
        "id": row["event_id"],
        "title": row["title"],
        "description": row["description"] or "",
        "date": row["event_date"].isoformat() if row["event_date"] else "",
        "time": str(row["event_time"]) if row["event_time"] else "",
        "venue": row["venue"] or "",
        "max_participants": row["max_participants"] or 0,
        "current_participants": row["current_participants"] or 0,
        "organizer": row["organizer"] or "Admin",
        "status": row["status"] or "Upcoming",
    }


def fetch_events():
    cursor = get_cursor()
    cursor.execute(
        """
        SELECT
            e.event_id,
            e.title,
            e.description,
            e.event_date,
            e.event_time,
            e.venue,
            e.max_participants,
            e.status,
            COALESCE(o.name, 'Admin') AS organizer,
            COUNT(r.registration_id) AS current_participants
        FROM events e
        LEFT JOIN organizers o ON o.organizer_id = e.organizer_id
        LEFT JOIN registrations r ON r.event_id = e.event_id
        GROUP BY e.event_id
        ORDER BY e.event_date, e.event_time
        """
    )
    events = [serialize_event(row) for row in cursor.fetchall()]
    cursor.close()
    return events


def get_default_organizer_id():
    cursor = get_cursor()
    cursor.execute("SELECT organizer_id FROM organizers ORDER BY organizer_id LIMIT 1")
    organizer = cursor.fetchone()
    cursor.close()
    return organizer["organizer_id"] if organizer else None


@app.route('/')
def home():
    return render_template('index.html', initial_data={"events": fetch_events()})


@app.get('/api/events')
def api_events():
    return jsonify(fetch_events())


@app.post('/api/events')
def create_event():
    data = request.get_json() or {}
    cursor = get_cursor()
    cursor.execute(
        """
        INSERT INTO events
            (organizer_id, title, description, event_date, event_time, venue, max_participants, status)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, 'Upcoming')
        """,
        (
            get_default_organizer_id(),
            data.get("title"),
            data.get("description"),
            data.get("date"),
            data.get("time"),
            data.get("venue"),
            data.get("max_participants"),
        ),
    )
    db.commit()
    event_id = cursor.lastrowid
    cursor.close()
    event = next((event for event in fetch_events() if event["id"] == event_id), None)
    return jsonify(event), 201


@app.put('/api/events/<int:event_id>')
def update_event(event_id):
    data = request.get_json() or {}
    cursor = get_cursor()
    cursor.execute(
        """
        UPDATE events
        SET title = %s,
            description = %s,
            event_date = %s,
            event_time = %s,
            venue = %s,
            max_participants = %s
        WHERE event_id = %s
        """,
        (
            data.get("title"),
            data.get("description"),
            data.get("date"),
            data.get("time"),
            data.get("venue"),
            data.get("max_participants"),
            event_id,
        ),
    )
    db.commit()
    cursor.close()
    event = next((event for event in fetch_events() if event["id"] == event_id), None)
    return (jsonify(event), 200) if event else (jsonify({"error": "Event not found"}), 404)


@app.post('/api/register')
def register_participant():
    data = request.get_json() or {}
    cursor = get_cursor()

    cursor.execute("SELECT event_id, max_participants FROM events WHERE event_id = %s", (data.get("event_id"),))
    event = cursor.fetchone()
    if not event:
        cursor.close()
        return jsonify({"error": "Event not found"}), 404

    cursor.execute("SELECT COUNT(*) AS count FROM registrations WHERE event_id = %s", (data.get("event_id"),))
    if cursor.fetchone()["count"] >= event["max_participants"]:
        cursor.close()
        return jsonify({"error": "Event is full"}), 409

    cursor.execute("SELECT participant_id FROM participants WHERE email = %s", (data.get("email"),))
    participant = cursor.fetchone()
    if participant:
        participant_id = participant["participant_id"]
    else:
        cursor.execute(
            """
            INSERT INTO participants (full_name, email, phone, organization)
            VALUES (%s, %s, %s, %s)
            """,
            (data.get("name"), data.get("email"), data.get("phone"), data.get("organization")),
        )
        participant_id = cursor.lastrowid

    cursor.execute(
        """
        SELECT registration_id
        FROM registrations
        WHERE event_id = %s AND participant_id = %s
        """,
        (data.get("event_id"), participant_id),
    )
    if cursor.fetchone():
        cursor.close()
        return jsonify({"error": "You are already registered for this event"}), 409

    cursor.execute(
        """
        INSERT INTO registrations (event_id, participant_id, payment_status)
        VALUES (%s, %s, 'Registered')
        """,
        (data.get("event_id"), participant_id),
    )
    db.commit()
    cursor.close()
    return jsonify({"message": "Registration saved", "events": fetch_events()}), 201

if __name__ == '__main__':
    app.run(debug=True)
