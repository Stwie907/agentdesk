import time

from app.workers.execution_worker import execute_agent
from app.database import SessionLocal
from app.models.execution import Execution


def run_pending_tasks():

    while True:

        db = SessionLocal()

        tasks = (
            db.query(Execution)
            .filter(
                Execution.status=="pending"
            )
            .all()
        )

        for task in tasks:

            print(
                f"Running execution {task.id}"
            )

            execute_agent(task.id)


        db.close()


        time.sleep(5)


if __name__ == "__main__":
    run_pending_tasks()
