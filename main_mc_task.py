from fastapi import FastAPI, BackgroundTasks
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from biz.task.mc_task import execute_task
from utils.logger_utils import LoggerFactory

logger = LoggerFactory.get_logger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/mc_task/create")
def graph_import_pg(data: dict, background_tasks: BackgroundTasks):
    logger.info(f"Received task creation request: {data}")
    try:
        assert "task_type" in data, "task_type is required."
        assert "task_ext" in data, "task_ext is required."
        assert "creator" in data, "creator is required."
        background_tasks.add_task(
            execute_task,
            data["task_type"],
            data["task_ext"],
            data.get("task_desc"),
            data.get("creator")
        )
        return JSONResponse(content={"rtn_code": "0000", "rtn_msg": "Task created."})
    except Exception as e:
        return JSONResponse(content={"rtn_code": "9999", "rtn_msg": str(e)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7003)
