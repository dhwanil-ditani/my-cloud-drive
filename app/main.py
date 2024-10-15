import shutil
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Response, UploadFile
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
from starlette import responses
from starlette.status import (
    HTTP_200_OK,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

sqlite_file_name = "db.sqlite3"
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args, echo=True)


def get_session():
    with Session(engine, autobegin=False) as session:
        session.begin()
        yield session
        if session.in_transaction():
            session.commit()


SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


class FolderBase(SQLModel):
    name: str


class Folder(FolderBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="folder.id")
    parent: Optional["Folder"] = Relationship(
        back_populates="children", sa_relationship_kwargs=dict(remote_side="Folder.id")
    )
    children: list["Folder"] = Relationship(back_populates="parent")
    files: list["File"] = Relationship(back_populates="parent")


class FolderResponse(FolderBase):
    id: int
    files: list["File"]


class FileBase(SQLModel):
    name: str
    content_type: str
    size: int
    parent_id: int | None


class File(FileBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="folder.id")
    parent: Optional["Folder"] = Relationship(back_populates="files")


class FileResponse(FileBase):
    id: int


app = FastAPI(lifespan=lifespan)


@app.get("/files", response_model=list[FileResponse])
def list_files(session: SessionDep):
    stmt = select(File)
    return session.exec(stmt).all()


@app.post("/files/upload", response_model=FileResponse)
async def upload_file(
    file: UploadFile, session: SessionDep, folder_id: int | None = Form(default=0)
):
    if folder_id is not None:
        parent = session.get(Folder, folder_id)
        if not parent:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND, detail="Parent folder not found."
            )
    new_file = File(
        name=file.filename,
        content_type=file.content_type,
        size=file.size,
        parent_id=folder_id,
    )
    session.add(new_file)
    session.flush()
    session.refresh(new_file)
    try:
        file_path = "./data/" + str(new_file.id) + "." + new_file.name.split(".")[-1]
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        session.rollback()
        print(e)
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="There was an error uploading the file",
        )
    finally:
        file.file.close()
    return new_file


@app.get("/files/{file_id}", response_model=FileResponse)
def get_file(file_id: int, session: SessionDep):
    file = session.get(File, file_id)
    if not file:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found.")
    return file


@app.get("/files/{file_id}/download")
def download_file(file_id: int, session: SessionDep):
    file = session.get(File, file_id)
    if not file:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found.")
    file_path = "./data/" + str(file.id) + "." + file.name.split(".")[-1]
    return responses.FileResponse(
        file_path, media_type=file.content_type, filename=file.name
    )


@app.delete("/files/{file_id}")
def delete_file(file_id: int, session: SessionDep):
    file = session.get(File, file_id)
    if not file:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found.")
    session.delete()
    session.flush()
    return Response(
        status_code=HTTP_200_OK,
    )


@app.get("/folders", response_model=list[Folder])
def list_folder(session: SessionDep):
    stmt = select(Folder)
    return session.exec(stmt).all()


@app.get("/folders/{folder_id}")
def get_folder(folder_id: int, session: SessionDep):
    folder = session.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Folder not found.")
    response = {
        "id": folder.id,
        "name": folder.name,
        "parent": [],
        "files": list(
            map(
                lambda x: {
                    "id": x.id,
                    "name": x.name,
                    "content_type": x.content_type,
                    "size": x.size,
                },
                folder.files,
            )
        ),
        "folders": list(
            map(
                lambda x: {"id": x.id, "name": x.name},
                folder.children,
            )
        ),
    }
    parent = folder.parent
    while parent:
        response["parent"].append({"id": parent.id, "name": parent.name})
        parent = parent.parent
    return response


@app.post("/folders")
def create_folder(
    folder_name: Annotated[str, Body()],
    session: SessionDep,
    parent_id: int | None = Body(default=None),
):
    if parent_id is not None:
        parent = session.get(Folder, parent_id)
        if not parent:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND, detail="Parent folder not found."
            )
    folder = Folder(name=folder_name, parent_id=parent_id)
    session.add(folder)
    session.flush()
    session.refresh(folder)
    return folder
