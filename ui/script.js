async function getFolderData(folder_id) {
    const response = await fetch("http://localhost:8000/folders/" + folder_id);
}