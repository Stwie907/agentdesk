from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.schemas.agent import AgentCreate


def create_agent(
    db: Session,
    agent: AgentCreate
):

    db_agent = Agent(
        name=agent.name,
        model=agent.model,
        description=agent.description,
        project_id=agent.project_id
    )

    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    return db_agent



def get_agent(
    db: Session,
    agent_id:int
):

    return (
        db.query(Agent)
        .filter(
            Agent.id == agent_id
        )
        .first()
    )


# 新增
def get_agents(
    db: Session
):

    return (
        db.query(Agent)
        .all()
    )
def delete_agent(
    db: Session,
    agent_id: int
):

    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id
        )
        .first()
    )

    if not agent:
        return None

    db.delete(agent)
    db.commit()

    return agent
