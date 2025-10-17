from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
from textblob import TextBlob
import sqlite3
from datetime import datetime
import uvicorn

app = FastAPI(title="University Notification Chatbot Backend")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def init_db():
    conn = sqlite3.connect("notifications.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  source TEXT,
                  content TEXT,
                  priority TEXT,
                  received_at TEXT,
                  processed BOOLEAN)''')
    conn.commit()
    conn.close()

init_db()

# Pydantic models for request/response
class Notification(BaseModel):
    source: str
    content: str

class NotificationResponse(BaseModel):
    id: int
    source: str
    content: str
    priority: str
    received_at: str
    processed: bool

# Priority classification logic
def classify_notification(content: str) -> str:
    blob = TextBlob(content.lower())
    # Define keywords for urgency
    urgent_keywords = ["urgent", "deadline", "important", "exam", "submission", "today", "tomorrow"]
    medium_keywords = ["assignment", "lecture", "meeting", "discussion"]
    
    # Check for urgent keywords
    if any(keyword in content.lower() for keyword in urgent_keywords):
        return "HIGH"
    # Check for medium priority
    elif any(keyword in content.lower() for keyword in medium_keywords):
        return "MEDIUM"
    # Sentiment analysis for additional context
    elif blob.sentiment.polarity < -0.2:  # Negative sentiment might indicate urgency
        return "HIGH"
    else:
        return "LOW"

# API Endpoints
@app.post("/notifications/", response_model=NotificationResponse)
async def add_notification(notification: Notification):
    priority = classify_notification(notification.content)
    received_at = datetime.utcnow().isoformat()
    
    conn = sqlite3.connect("notifications.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO notifications (source, content, priority, received_at, processed) VALUES (?, ?, ?, ?, ?)",
        (notification.source, notification.content, priority, received_at, False)
    )
    conn.commit()
    
    notification_id = c.lastrowid
    c.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,))
    result = c.fetchone()
    conn.close()
    
    return {
        "id": result[0],
        "source": result[1],
        "content": result[2],
        "priority": result[3],
        "received_at": result[4],
        "processed": bool(result[5])
    }

@app.get("/notifications/", response_model=List[NotificationResponse])
async def get_notifications(priority: str = None, limit: int = 10):
    conn = sqlite3.connect("notifications.db")
    c = conn.cursor()
    
    if priority:
        c.execute("SELECT * FROM notifications WHERE priority = ? AND processed = ? ORDER BY received_at DESC LIMIT ?",
                 (priority.upper(), False, limit))
    else:
        c.execute("SELECT * FROM notifications WHERE processed = ? ORDER BY received_at DESC LIMIT ?",
                 (False, limit))
    
    results = c.fetchall()
    conn.close()
    
    return [
        {
            "id": row[0],
            "source": row[1],
            "content": row[2],
            "priority": row[3],
            "received_at": row[4],
            "processed": bool(row[5])
        } for row in results
    ]

@app.put("/notifications/{notification_id}/processed")
async def mark_notification_processed(notification_id: int):
    conn = sqlite3.connect("notifications.db")
    c = conn.cursor()
    c.execute("UPDATE notifications SET processed = ? WHERE id = ?", (True, notification_id))
    conn.commit()
    conn.close()
    
    if c.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"message": f"Notification {notification_id} marked as processed"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, port=8000)