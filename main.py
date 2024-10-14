from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Response, UploadFile
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
from starlette.status import HTTP_200_OK, HTTP_404_NOT_FOUND

sqlite_file_name = "db.sqlite3"
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield
    # SQLModel.metadata.drop_all(engine)


class FolderBase(SQLModel):
    name: str


class Folder(FolderBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="folder.id")
    parent: Optional["Folder"] = Relationship(back_populates="child")
    child: list["Folder"] = Relationship(back_populates="parent")
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
    data: bytes
    parent_id: int | None = Field(default=None, foreign_key="folder.id")
    parent: Optional["Folder"] = Relationship(back_populates="files")


class FileResponse(FileBase):
    id: int


app = FastAPI(lifespan=lifespan)


@app.get("/files/", response_model=list[FileResponse])
def list_files(session: SessionDep):
    stmt = select(File)
    return session.exec(stmt).all()


@app.post("/files/upload", response_model=FileResponse)
async def upload_file(file: UploadFile, session: SessionDep):
    file = File(
        name=file.filename,
        content_type=file.content_type,
        size=file.size,
        data=await file.read(),
    )
    session.add(file)
    session.commit()
    session.refresh(file)
    return file


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
    return Response(
        content=file.data,
        media_type=file.content_type,
        status_code=HTTP_200_OK,
        headers={"Content-Disposition": f"attachment; filename={file.name}"},
    )


@app.delete("/files/{file_id}")
def delete_file(file_id: int, session: SessionDep):
    file = session.get(File, file_id)
    if not file:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="File not found.")
    session.delete()
    session.commit()
    return Response(
        status_code=HTTP_200_OK,
    )


@app.get("/folders")
def list_folder(session: SessionDep):
    stmt = select(Folder)
    return session.exec(stmt).all()


@app.get("/folders/{folder_id}", response_model=FolderResponse)
def get_folder(folder_id: int, session: SessionDep):
    folder = session.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Folder not found.")
    return {
        "id": folder.id,
        "name": folder.name,
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
    }


@app.post("/folders")
def create_folder(folder_name: str, session: SessionDep):
    folder = Folder(name=folder_name)
    session.add(folder)
    session.commit()
    session.refresh(folder)
    return folder
