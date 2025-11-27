from fastapi import FastAPI, Depends, Body, Query, status, responses, HTTPException, Response, Path, File, UploadFile, Request
import json
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from pydantic import HttpUrl, BaseModel
from datetime import datetime, date, timedelta
from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Annotated, Any, Union, List
from contextlib import asynccontextmanager
from models import TaskIn, TaskInDB, Status, TasksInfo
from dotenv import load_dotenv
from perplexity import Perplexity
load_dotenv()



# Defining SQLModel tables

class Users(SQLModel, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    tg_id: int = Field(unique=True)
    username: Union[str, None] = None
    user_since: datetime = Field(default_factory=date.today)

class TasksDB(SQLModel, table=True):
    id: Union[int, None] = Field(default=None, primary_key=True)
    tg_id: int
    status: str
    description: Union[str, None] = Field(default=None,
                                          max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now().replace(microsecond=0))
    deadline: Union[datetime, None] = Field(default=None)


class UsageLimit(SQLModel, table=True):
    user_id: int = Field(primary_key=True)
    day: Union[date, None] = Field(default=None)
    requests_count: int
    unlimited: bool = Field(default=False)


# Setting up database

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)

# A client for working with Perplexity's "Sonar" model

client = Perplexity()


# Defining database session dependencies

def get_session():
    with Session(engine) as session:
        yield session
SessionDep = Annotated[Session, Depends(get_session)]

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)



# Managing program's lifespan
# Database and tables will be created (if they don't exist yet) before the main code actually starts

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("App has started")
    create_db_and_tables()
    yield
    print("App has stopped")





app = FastAPI(lifespan=lifespan)



# Handling validation error for clearer exception output

@app.exception_handler(RequestValidationError)
async def validation_exception_error(request, exc):
    return responses.JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail" : exc.errors(), "body": exc.body})
    )



# API for whenever a user makes new AI advice request

@app.put("/new_request/")
async def new_user_request(user_id: int, session: SessionDep) -> Any:
    query = select(UsageLimit).where(UsageLimit.user_id==user_id)
    resp = session.exec(query).one()
    
    resp.requests_count += 1
    session.commit()
    session.refresh(resp)
    return responses.JSONResponse(content=f"User id{user_id} has successfully made a new request")


# API for checking user's daily AI advice feature limit

@app.get("/check_limit/")
async def limit_check(user_id: int, session: SessionDep) -> Any:

    today = date.today()
    query=select(UsageLimit).where(UsageLimit.user_id==user_id)
    resp = session.exec(query).one()

    if resp.unlimited:
        return responses.JSONResponse(content={"limit": "good"})

    if resp.day != today:
        resp.sqlmodel_update({"day": today, "requests_count": 0})
        session.commit()

    if(resp.requests_count >= 5):
        return responses.JSONResponse(content={"limit": "bad"})

    
    return responses.JSONResponse(content={"limit": "good"})


# API for granting unlimited rights on requesting AI advice

@app.post("/give_unlimited/")
async def set_unlimited(user_id: int, session: SessionDep) -> Any:
    query = select(UsageLimit).where(UsageLimit.user_id==user_id)
    resp = session.exec(query).one()
    resp.sqlmodel_update({"unlimited": True})
    session.commit()

    return responses.JSONResponse(content=f"User id{user_id} has been granted unlimited role")    


# API for requesting an advice from Sonar

@app.get("/sonar/")
async def sonar_response(user_id: int, task_id: int, session: SessionDep):
    query = select(TasksDB).where(TasksDB.tg_id == user_id)
    result = session.exec(query).all()

    for i, item in enumerate(result):
        if i+1 == task_id:
            description = item.description
            break


    taskDescription = description
    prompt = "Give a concise (no more than 70 words! and no text formatting, but separate paragrphs, also dont include resource links or hyperlinks. plain text only) but insightful advice for this task(explain how to plan, what steps to take, how to achieve the best result). Do not give help on anythin illegal, discriminating ( race, religion, etc., " + "details: " + str(taskDescription)  + " Answer in RUSSIAN" 
    
    answer = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="sonar",
    )

    advice = f"Совет: {answer.choices[0].message.content}"

    return responses.JSONResponse(content=advice, status_code=status.HTTP_202_ACCEPTED)


# Creating and adding a new user to database

@app.post("/user/new/")
async def new_user(tg_id: int, name: str, session: SessionDep):
    exists1 = session.scalar(select(Users).where(Users.tg_id == tg_id))
    exists2 = session.scalar(select(UsageLimit).where(UsageLimit.user_id==tg_id))


    if not exists1:
        userN = Users(tg_id=tg_id, username=name)
        session.add(userN)
        session.commit()

    if not exists2:
        userUL = UsageLimit(user_id=tg_id, requests_count=0)
        session.add(userUL)
        session.commit()


# API for getting the amount of total, done, and incomplete tasks

@app.get("/tasks/user/")
async def tasks_info(user_id: int, session: SessionDep) -> TasksInfo:
    query = select(TasksDB).where(TasksDB.tg_id == user_id)
    resp = session.exec(query).all()

    total = len(resp)
    done = 0
    incomplete = 0

    for item in resp:
        if item.status == "done":
            done += 1
        
        elif item.status == "incomplete":
            incomplete += 1

    return TasksInfo(total=total, done=done, incomplete=incomplete)

    
# API for getting tasks of all users

@app.get("/tasks/all")
async def get_all_tasks(session: SessionDep):
    query = select(TasksDB)
    result = session.exec(query).all()

    return result



# API for getting user's tasks amount

@app.get("/tasks/count/{tg_id}", status_code=status.HTTP_200_OK)
async def get_tasks_count(tg_id: int, session: SessionDep) -> Any:
    query = select(TasksDB).where(TasksDB.tg_id==tg_id)
    allTasks = list(session.exec(query).all())
    return responses.JSONResponse(content={"max_id": len(allTasks)})


# API for changing task's status from incomplete to done

@app.put("/tasks/")
async def change_status(user_id: int, task_id: int, session: SessionDep) -> Any:
    query = select(TasksDB).where(TasksDB.tg_id==user_id)
    resp = session.exec(query).all()
    for i, item in enumerate(resp):
        if i+1 == task_id:
            task = item
            break

    task.sqlmodel_update({"status": "done"})
    session.commit()
    dt = task.deadline
    if dt is None:
        return
    s = dt.isoformat()
    return responses.JSONResponse(content={"description": task.description, "deadline": s})


# API for getting all user's tasks

@app.get("/tasks/{tg_id}", response_model=list[TasksDB], status_code=status.HTTP_200_OK)
async def get_tasks(tg_id: int, session: SessionDep) -> Any:
    query = select(TasksDB).where(TasksDB.tg_id==tg_id)
    allTasks = list(session.exec(query).all())
    return allTasks
        

# API for creating a new task

@app.post("/tasks/", response_model_exclude={"tg_id"} ,status_code=status.HTTP_201_CREATED)
async def create_task(item: Annotated[TaskIn, Body(title="get_task_data",
                                                 description="receiving a json with item's data")], session: SessionDep) -> TaskIn:
    deadline = None

    if(item.deadline):
        deadline = datetime.now().replace(microsecond=0) + timedelta(days=item.deadline)

    taskDB = TasksDB(
       tg_id =item.tg_id,
       status = "incomplete",
       description = item.description,
       deadline = deadline,
    )
        

    session.add(taskDB)
    session.commit()
    return item


# API for deleting a task

@app.delete("/tasks/delete/", status_code=status.HTTP_200_OK)
async def delete_task(item_id: Annotated[int, Query()], session: SessionDep) -> Any:
    query = select(TasksDB).where(TasksDB.id == item_id)
    result = session.exec(query)
    task = result.one()
    session.delete(task)
    session.commit()


    
    return responses.JSONResponse(content="Task has been deleted")
    


