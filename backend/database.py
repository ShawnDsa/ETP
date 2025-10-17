from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from textblob import TextBlob
from datetime import datetime
import motor.motor_asyncio
from bson import ObjectId
import uvicorn

app = FastAPI(title="University Notification Chatbot Backend")

# MongoDB setup
MONGO_DETAILS = "mongodb://localhost:27017"  # Change if needed
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DETAILS)
db = client.university_notifications
notifications_collection = db.get_collection("notifications")


# Pydantic models for request/response

class Notification(BaseModel):
    source: str
    content: str


class NotificationResponse(BaseModel):
    id: str = Field(..., alias="_id")
    source: str
    content: str
    priority: str
    received_at: str
    processed: bool


# Helper function to convert MongoDB document to Pydantic model friendly dict
def notification_helper(notification) -> dict:
    return {
        "id": str(notification["_id"]),
        "source": notification["source"],
        "content": notification["content"],
        "priority": notification["priority"],
        "received_at": notification["received_at"],
        "processed": notification["processed"]
    }


# Priority classification logic (same as your original)
def classify_notification(content: str) -> str:
    blob = TextBlob(content.lower())
    urgent_keywords = ["urgent", "deadline", "important", "exam", "submission", "today", "tomorrow"]
    medium_keywords = ["assignment", "lecture", "meeting", "discussion"]

    if any(keyword in content.lower() for keyword in urgent_keywords):
        return "HIGH"
    elif any(keyword in content.lower() for keyword in medium_keywords):
        return "MEDIUM"
    elif blob.sentiment.polarity < -0.2:
        return "HIGH"
    else:
        return "LOW"


# API Endpoints
@app.post("/notifications/", response_model=NotificationResponse)
async def add_notification(notification: Notification):
    priority = classify_notification(notification.content)
    received_at = datetime.utcnow().isoformat()
    
    new_notification = {
        "source": notification.source,
        "content": notification.content,
        "priority": priority,
        "received_at": received_at,
        "processed": False
    }
    result = await notifications_collection.insert_one(new_notification)
    created_notification = await notifications_collection.find_one({"_id": result.inserted_id})
    return notification_helper(created_notification)


@app.get("/notifications/", response_model=List[NotificationResponse])
async def get_notifications(priority: Optional[str] = None, limit: int = 10):
    query = {"processed": False}
    if priority:
        query["priority"] = priority.upper()
    
    notifications_cursor = notifications_collection.find(query).sort("received_at", -1).limit(limit)
    notifications = []
    async for notification in notifications_cursor:
        notifications.append(notification_helper(notification))
    return notifications


@app.put("/notifications/{notification_id}/processed")
async def mark_notification_processed(notification_id: str):
    result = await notifications_collection.update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"processed": True}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")

    return {"message": f"Notification {notification_id} marked as processed"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
