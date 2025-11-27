from typing import Annotated, Union
from pydantic import Field, BaseModel, HttpUrl
from enum import Enum
from datetime import datetime, date
from sqlmodel import SQLModel

class Status(str, Enum):
    done = "done"
    active = "active"
    incomplete = "incomplete"
    archived = "archived"

class TaskIn(SQLModel):
    tg_id: int
    description: Annotated[str, Field(default="None",
                                      title="task's detailed explanation",
                                      min_length=1,
                                      max_length=5000)]
    deadline: Union[int, None] = None

    

class TaskInDB(TaskIn):
    id: int
    deadline: Union[datetime, None] = None
    status: Annotated[Status, Field(default="incomplete")]


class TasksInfo(BaseModel):
    total: int
    done: int
    incomplete: int
    
    