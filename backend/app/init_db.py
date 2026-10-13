from app.database import Base, engine

from app.models import User, Project


print("Creating database tables...")


Base.metadata.create_all(
    bind=engine
)


print("Done.")
