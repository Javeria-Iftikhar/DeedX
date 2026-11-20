from app.database import Base, engine
from app import models  # IMPORTANT: ensures all tables are loaded

Base.metadata.create_all(bind=engine)

print("✅ All tables created successfully")